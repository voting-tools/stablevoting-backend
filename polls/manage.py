#
# Functions to manage polls
#

#
# Functions to manage polls
#

from fastapi import BackgroundTasks, File, UploadFile
import arrow
import random
from pymongo import AsyncMongoClient
import csv
import io
import os
import time
from bson import ObjectId
import humanize
import networkx as nx
from collections import defaultdict
from func_timeout import func_timeout, FunctionTimedOut

from pref_voting.profiles_with_ties import ProfileWithTies
from pref_voting.voting_methods import (
    split_cycle_defeat, stable_voting, split_cycle,
    minimax, copeland, MWSL, borda_for_profile_with_ties, approval_irv,
)
from polls.models import CreatePoll, UpdatePoll
from polls.helpers import generate_voter_ids
from messages.helpers import participate_email
from polls.voting import is_linear, generate_columns_from_profiles, stable_voting_with_explanations_, get_splitting_numbers, generate_csv_data

# UPDATED IMPORTS - removed fastapi_mail, added new email functions
from messages.conf import SKIP_EMAILS, send_email
import certifi

# MongoDB connection
mongo_details = os.getenv('MONGODB_URI')

# Check if we're in development (local MongoDB doesn't use SSL)
if mongo_details and ('localhost' in mongo_details or '127.0.0.1' in mongo_details):
    # Local connection without SSL
    client = AsyncMongoClient(mongo_details)
else:
    # Production connection with SSL
    client = AsyncMongoClient(mongo_details, tlsCAFile=certifi.where(), tls=True)

data_base = os.getenv('MONGO_DB_NAME', 'StableVoting')
db = client[data_base].Polls


def _multiple_vote_allowed(pwd):
    """True only when the debug password is set in the environment and matches."""
    expected = os.getenv('ALLOW_MULTIPLE_VOTE_PWD')
    return expected is not None and pwd == expected


def superuser_pwd_valid(pwd):
    """True only when SUPERUSER_PWD is set in the environment and matches."""
    expected = os.getenv('SUPERUSER_PWD')
    return bool(expected) and pwd == expected


async def superuser_list_polls():
    """Summary of every poll for the (password-gated) super-user poll list.

    Returns id, title, owner id, candidate count, ballot count, and status —
    counted server-side so the full ballot/candidate arrays are never shipped.
    """
    pipeline = [
        {"$project": {
            "_id": 0,
            "id": {"$toString": "$_id"},
            "title": {"$ifNull": ["$title", "(untitled)"]},
            "oid": "$owner_id",
            "nc": {"$size": {"$ifNull": ["$candidates", []]}},
            "nb": {"$size": {"$ifNull": ["$ballots", []]}},
            "done": {"$ifNull": ["$is_completed", False]},
            "priv": {"$ifNull": ["$is_private", False]},
        }},
        {"$sort": {"nb": -1}},
    ]
    cursor = await db.aggregate(pipeline)
    return await cursor.to_list(length=None)


def _sv_winners_only(prof, curr_cands=None):
    """Stable Voting winners via the site's own routine (split-cycle based, so it
    stays feasible on large polls) — matches what the results page shows, unlike
    pref_voting's raw stable_voting which recurses over every candidate."""
    ws, _, _ = stable_voting_with_explanations_(prof, curr_cands=curr_cands)
    return ws


_SU_METHODS = None
def _su_methods():
    global _SU_METHODS
    if _SU_METHODS is None:
        _SU_METHODS = {
            "Minimax": minimax, "Copeland": copeland, "Stable Voting": _sv_winners_only,
            "Split Cycle": split_cycle, "MWSL": MWSL,
            "Borda": borda_for_profile_with_ties, "IRV": approval_irv,
        }
    return _SU_METHODS


def _ballot_type(rmap, ncand):
    ranked = list(rmap.keys())
    if len(ranked) == 0:
        return None
    ranks = list(rmap.values())
    has_ties = len(set(ranks)) != len(ranks)
    truncated = len(ranked) < ncand
    return {"linear": (not has_ties) and (not truncated), "truncated": truncated,
            "ties": has_ties, "bullet": len(ranked) == 1}


def _plurality_ws(prof):
    """Approval-at-top plurality winners: each voter gives one point to every
    candidate at their top (first) rank; a voter tied k-at-top counts for all k.
    Returns the set of top-scoring candidates (as strings), or None."""
    scores = {c: 0 for c in prof.candidates}
    for r, cnt in zip(prof.rankings, prof.rcounts):
        if len(r.rmap) == 0:
            continue
        top = min(r.rmap.values())
        for c, rk in r.rmap.items():
            if rk == top and c in scores:
                scores[c] += cnt
    if not scores or max(scores.values()) == 0:
        return None
    mx = max(scores.values())
    return frozenset(str(c) for c in scores if scores[c] == mx)


_SU_STATS_CACHE = {"data": None, "ts": 0.0}


async def superuser_stats():
    """Analytics over every poll for the super-user dashboard: totals, size and
    Condorcet distributions, poll-creation time series, ballot-type mix, and
    pairwise winner disagreement across voting methods. Cached for 5 minutes
    since the full computation takes a few seconds."""
    if _SU_STATS_CACHE["data"] is not None and (time.time() - _SU_STATS_CACHE["ts"]) < 300:
        return _SU_STATS_CACHE["data"]
    METHODS = _su_methods()
    MNAMES = list(METHODS.keys())

    def winset(fn, prof):
        try:
            return frozenset(str(c) for c in func_timeout(2, fn, args=(prof,)))
        except BaseException:
            return None

    CAND_B = [(2, 2, "2"), (3, 3, "3"), (4, 4, "4"), (5, 5, "5"), (6, 7, "6-7"),
              (8, 10, "8-10"), (11, 15, "11-15"), (16, 10**9, "16+")]
    VOTER_B = [(1, 4, "1-4"), (5, 9, "5-9"), (10, 24, "10-24"), (25, 49, "25-49"),
               (50, 99, "50-99"), (100, 10**9, "100+")]

    total = with_ballots = total_votes = 0
    cand_counts, voter_counts = [], []
    cand_hist, voter_hist, by_month, pair_diff = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    wset_sizes, wset_counts = defaultdict(float), defaultdict(int)
    cw = wcw = cl = wcl = cycle = restricted = 0
    closed_ct = private_ct = 0
    sv_unique = sv_tied = plur_ne = plur_base = 0
    bt_sums = {"linear": 0.0, "truncated": 0.0, "ties": 0.0, "bullet": 0.0}
    bt_polls = 0

    cursor = db.find({}, {"candidates": 1, "ballots": 1, "is_completed": 1, "is_private": 1})
    async for doc in cursor:
        total += 1
        if doc.get("is_completed"):
            closed_ct += 1
        if doc.get("is_private"):
            private_ct += 1
        cands = doc.get("candidates", []) or []
        ballots = doc.get("ballots", []) or []
        ncand, nb = len(cands), len(ballots)
        for lo, hi, lbl in CAND_B:
            if lo <= ncand <= hi:
                cand_hist[lbl] += 1
                break
        for lo, hi, lbl in VOTER_B:
            if lo <= nb <= hi:
                voter_hist[lbl] += 1
                break
        try:
            by_month[doc["_id"].generation_time.strftime("%Y-%m")] += 1
        except Exception:
            pass
        if nb == 0 or ncand < 2:
            continue
        with_ballots += 1
        total_votes += nb
        cand_counts.append(ncand)
        voter_counts.append(nb)

        cand_to_cidx = {c: i for i, c in enumerate(cands)}
        try:
            prof = ProfileWithTies([
                {cand_to_cidx[c]: rank for c, rank in b["ranking"].items() if c in cand_to_cidx}
                for b in ballots])
        except Exception:
            continue
        if not any(len(r.rmap) > 0 for r in prof.rankings):
            continue

        types = [t for t in (_ballot_type(b["ranking"], ncand) for b in ballots) if t]
        if types:
            for k in bt_sums:
                bt_sums[k] += sum(1 for t in types if t[k]) / len(types)
            bt_polls += 1

        try:
            ci = list(prof.candidates)
            m = {a: {b: prof.margin(a, b) for b in ci} for a in ci}
            if prof.condorcet_winner() is not None:
                cw += 1
            if any(all(m[o][c] <= 0 for o in ci if o != c) for c in ci):
                wcw += 1
            if any(all(m[o][c] > 0 for o in ci if o != c) for c in ci):
                cl += 1
            if any(all(m[c][o] <= 0 for o in ci if o != c) for c in ci):
                wcl += 1
            g = nx.DiGraph()
            g.add_nodes_from(ci)
            for x in ci:
                for y in ci:
                    if x != y and m[x][y] > 0:
                        g.add_edge(x, y)
            if not nx.is_directed_acyclic_graph(g):
                cycle += 1
        except Exception:
            pass

        # Stable Voting winner set (unique vs. tied) + plurality-vs-SV agreement,
        # using the site's own SV routine so it matches the results page.
        sv = winset(_sv_winners_only, prof)
        if sv is not None:
            if len(sv) == 1:
                sv_unique += 1
            else:
                sv_tied += 1
            try:
                pl = _plurality_ws(prof)
            except Exception:
                pl = None
            if pl is not None:
                plur_base += 1
                if pl != sv:
                    plur_ne += 1

        if nb >= 5 and ncand >= 3:
            ws = {name: winset(fn, prof) for name, fn in METHODS.items()}
            restricted += 1
            for name in MNAMES:
                if ws[name] is not None:
                    wset_sizes[name] += len(ws[name])
                    wset_counts[name] += 1
            for i in range(len(MNAMES)):
                for j in range(i + 1, len(MNAMES)):
                    a, b = MNAMES[i], MNAMES[j]
                    if ws[a] is not None and ws[b] is not None and ws[a] != ws[b]:
                        pair_diff[a + "|" + b] += 1

    def summary(xs):
        if not xs:
            return {"mean": 0, "median": 0, "std": 0, "max": 0}
        s = sorted(xs)
        n = len(s)
        med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
        mean = sum(s) / n
        std = (sum((x - mean) ** 2 for x in s) / n) ** 0.5
        return {"mean": round(mean, 1), "median": med, "std": round(std, 1), "min": s[0], "max": s[-1]}

    result = {
        "total": total,
        "withb": with_ballots,
        "total_votes": total_votes,
        "size": {"voters": summary(voter_counts), "candidates": summary(cand_counts)},
        "cand": dict(cand_hist),
        "voter": dict(voter_hist),
        "cond": {"cw": cw, "weak_cw": wcw, "cl": cl, "weak_cl": wcl, "cycle": cycle, "base": with_ballots},
        "status": {"closed": closed_ct, "open": total - closed_ct, "private": private_ct, "public": total - private_ct},
        "sv": {"unique": sv_unique, "tied": sv_tied, "base": sv_unique + sv_tied},
        "plurality": {"ne_sv": plur_ne, "base": plur_base},
        "ts": sorted(by_month.items()),
        "pair": dict(pair_diff),
        "restricted": restricted,
        "method_winset": {n: round(wset_sizes[n] / wset_counts[n], 3) for n in MNAMES if wset_counts[n]},
        "bt": {k: (bt_sums[k] / bt_polls if bt_polls else 0) for k in bt_sums},
    }
    _SU_STATS_CACHE["data"] = result
    _SU_STATS_CACHE["ts"] = time.time()
    return result


async def create_poll(background_tasks: BackgroundTasks, poll_data: CreatePoll):
    """Create a poll."""
    print("HERE!!!!! creating a poll...")
    now = arrow.now()
    print(now.format('YYYY-MM-DD HH:mm'))
    voter_ids = []
    voter_email_map = {}
    if poll_data.is_private: 
        voter_ids = generate_voter_ids(len(poll_data.voter_emails))
        voter_email_map = {vid: email for vid, email in zip(voter_ids, poll_data.voter_emails)}

    owner_id = generate_voter_ids(1)[0]
    poll = {
        "title": poll_data.title,
        "description": poll_data.description,
        "hide_description": poll_data.hide_description,
        "candidates": poll_data.candidates,
        "is_private": poll_data.is_private,
        "voter_ids": voter_ids,
        "voter_email_map": voter_email_map,
        "owner_id": owner_id,
        "show_rankings": poll_data.show_rankings,
        "closing_datetime": poll_data.closing_datetime,
        "timezone": poll_data.timezone,
        "can_view_outcome_before_closing": poll_data.can_view_outcome_before_closing,
        "show_outcome": poll_data.show_outcome,
        "allow_multiple_votes": poll_data.allow_multiple_votes,
        "ballots": [],
        "is_completed": False,
        "result": None,
        "creation_dt": now.format('MMMM DD, YYYY @ HH:mm')
    }
    result = await db.insert_one(poll)

    if not SKIP_EMAILS:
        # UPDATED: Admin notification using new send_email
        background_tasks.add_task(
            send_email,
            to_email="stablevoting.org@gmail.com",
            subject="New Poll Created",
            html_body=f"""<p>Poll Created: https://stablevoting.org/results/{result.inserted_id}?oid={owner_id}</p>
            <p>vote: https://stablevoting.org/vote/{result.inserted_id}?oid={owner_id}</p>            
            <p>admin: https://stablevoting.org/admin/{result.inserted_id}?oid={owner_id}</p><p></p><p>{poll}</p>""",
            tag="admin-poll-created"
        )
        
        # Also send to Eric
        background_tasks.add_task(
            send_email,
            to_email="epacuit@umd.edu",
            subject="New Poll Created",
            html_body=f"""<p>Poll Created: https://stablevoting.org/results/{result.inserted_id}?oid={owner_id}</p>
            <p>vote: https://stablevoting.org/vote/{result.inserted_id}?oid={owner_id}</p>            
            <p>admin: https://stablevoting.org/admin/{result.inserted_id}?oid={owner_id}</p><p></p><p>{poll}</p>""",
            tag="admin-poll-created"
        )

        # UPDATED: Send voter invitations using new send_email
        for em, voter_id in zip(poll_data.voter_emails, voter_ids):
            print("sending email to ", em)
            link = f"https://stablevoting.org/vote/{result.inserted_id}?vid={voter_id}"
            print(participate_email(poll_data.title, poll_data.description, link))
            
            background_tasks.add_task(
                send_email,
                to_email=em,
                subject=f"Participate in the poll: {poll_data.title}",
                html_body=participate_email(poll_data.title, poll_data.description, link),
                tag="voter-invitation"
            )

    return {"id": str(result.inserted_id), "owner_id": owner_id}


async def update_poll(id, owner_id, poll_data: UpdatePoll, background_tasks: BackgroundTasks):
    """Update a poll. """

    if not ObjectId.is_valid(id):
        return {"error": "Poll not found."}
    document = await db.find_one({"_id": ObjectId(id)})
    poll_data = poll_data.model_dump()
    if document is None: # poll not found
        return {"error": "Poll not found."}
    else: 
        if owner_id != document["owner_id"]: 
            return {"error": "You do not have permission to modify the poll."}
        
        get_data = lambda field : poll_data[field] if poll_data[field] is not None else  document[field]

        new_voter_ids = []
        print("new_voter_emails", poll_data["new_voter_emails"])
        print("document is_private", document.get("is_private"))
        print("poll_data is_private", poll_data.get("is_private"))

        existing_voter_email_map = document.get("voter_email_map", {})
        updated_voter_email_map = existing_voter_email_map.copy()
        
        # Use the actual poll's privacy status, not the potentially None value from poll_data
        poll_is_private = get_data("is_private")
        print("poll_is_private (resolved):", poll_is_private)
        
        if poll_is_private and poll_data["new_voter_emails"] is not None and len(poll_data["new_voter_emails"]) > 0:
            print("HERE!!!") 
            new_voter_ids = generate_voter_ids(len(poll_data["new_voter_emails"]))                
            print("new voter ids ", new_voter_ids)
            new_voter_email_map = {vid: email for vid, email in zip(new_voter_ids, poll_data["new_voter_emails"])}

            # Get existing map and merge:
            existing_voter_email_map = document.get("voter_email_map", {})
            updated_voter_email_map = {**existing_voter_email_map, **new_voter_email_map}

        new_poll = {
            "title": get_data("title"),
            "description": get_data("description"),
            "hide_description": get_data("hide_description"),
            "is_private": get_data("is_private"),
            "voter_ids": document["voter_ids"] + new_voter_ids,
            "voter_email_map": updated_voter_email_map,
            "show_rankings": get_data("show_rankings"),
            "closing_datetime": get_data("closing_datetime") if poll_data["closing_datetime"] != "del" else None,
            "timezone": get_data("timezone"),
            "can_view_outcome_before_closing": get_data("can_view_outcome_before_closing"),
            "show_outcome": get_data("show_outcome"),
            "allow_multiple_votes": get_data("allow_multiple_votes"),
            "ballots": document["ballots"],
            "is_completed": get_data("is_completed"),
            "result": document["result"],
            "creation_dt": document["creation_dt"],
            }
        resp = {"success": "Poll updated."}
        if len(document["ballots"]) > 0: 
            new_poll["candidates"] = document["candidates"]
            if poll_data["candidates"] is not None:
                resp["message"] = "Since voters have submitted ballots, candidate names cannot be changed.   The other changes have been made to the poll." 
        else: 
            new_poll["candidates"] =  get_data("candidates") 
        
        result = await db.update_one({"_id": ObjectId(id)}, {"$set": new_poll})

        if not SKIP_EMAILS: 
            if len(new_voter_ids) > 0: 
                # UPDATED: Send emails to new voters using new send_email
                for em, voter_id in zip(poll_data["new_voter_emails"], new_voter_ids):
                    print("sending email to ", em)
                    link = f"https://stablevoting.org/vote/{id}?vid={voter_id}"

                    background_tasks.add_task(
                        send_email,
                        to_email=em,
                        subject=f'Participate in the poll: {new_poll["title"]}',
                        html_body=participate_email(new_poll["title"], new_poll["description"], link),
                        tag="voter-invitation-update"
                    )

    return resp

# All other functions remain the same - no email sending in them
async def delete_poll(id, oid):
    """Delete the poll given the owner id."""
    if not ObjectId.is_valid(id):
        return {"error": "Poll not found. Invalid poll id."}

    document = await db.find_one({"_id": ObjectId(id)})

    if document is None: 
        return {"error": "Poll not found."}

    if oid != document["owner_id"]: 
        return {"error": "You do not have permission to delete this poll."}

    result = await db.delete_one( {"_id": ObjectId(id), "owner_id": oid})
    if result.deleted_count == 0: 
        return {"error": "There was a problem.  The poll was not deleted."}
    else: 
        return {"success": "Poll deleted."}


async def poll_information(id, oid): 
    print("id ", id)
    print("oid ", oid)

    if not ObjectId.is_valid(id): 
        return {"error": "Poll not found."}

    document = await db.find_one({"_id": ObjectId(id)})  
    print(document) 

    if document is None: # poll not found
        return {"error": "Poll not found."}
    
    is_owner = document["owner_id"] == oid
    
    is_closed = poll_closed( 
        document.get("closing_datetime", None), 
        document.get("timezone", None))

    resp = {
        "is_owner": is_owner,
        "election_id": str(document["_id"]),
        "title": document.get("title", "n/a"),
        "description": document.get("description", "n/a"),
        "hide_description": document.get("hide_description", False),
        "num_ballots": len(document["ballots"]),
        "candidates": document.get("candidates", []),
        "is_private": document.get("is_private", False),
        "num_invited_voters": len(document.get("voter_ids", list())) if document.get("is_private", False) else None,
        "show_rankings": document.get("show_rankings", True),
        "allow_multiple_votes": document.get("allow_multiple_votes", False),
        "closing_datetime": document.get("closing_datetime", ""),
        "timezone": document.get("timezone", ""),
        "can_view_outcome_before_closing": document.get("can_view_outcome_before_closing", True),
        "show_outcome": document.get("show_outcome", True),
        "is_closed": is_closed,
        "is_completed": document.get("is_completed", False),
        "creation_dt": document.get("creation_dt", False),
        }
    
    if is_owner and document.get("is_private", False):
        voter_email_map = document.get("voter_email_map", {})
        voter_ids = document.get("voter_ids", [])
        email_send_counts = document.get("email_send_counts", {})
        
        voter_details = []
        if voter_email_map:
            for vid in voter_ids:
                email = voter_email_map.get(vid, "Email not available")
                voter_details.append({
                    "voter_id": vid,
                    "email": email,
                    "emailsSent": email_send_counts.get(email, 1)  # Default to 1 if not tracked
                })
        else:
            # Old polls
            for vid in voter_ids:
                voter_details.append({
                    "voter_id": vid,
                    "email": "Email not available (legacy poll)",
                    "emailsSent": 0
                })
        
        resp["voter_details"] = voter_details

    return resp

async def delete_voter(poll_id: str, voter_id: str, owner_id: str):
    """Delete a voter from a private poll."""
    if not ObjectId.is_valid(poll_id):
        return {"error": "Invalid poll ID."}
    
    document = await db.find_one({"_id": ObjectId(poll_id)})
    
    if document is None:
        return {"error": "Poll not found."}
    
    if document["owner_id"] != owner_id:
        return {"error": "Not authorized."}
    
    if not document.get("is_private", False):
        return {"error": "Can only manage voters in private polls."}
    
    # Get current voter lists
    voter_ids = document.get("voter_ids", [])
    voter_email_map = document.get("voter_email_map", {})
    
    if voter_id not in voter_ids:
        return {"error": "Voter not found."}
    
    # Remove voter_id from the list
    voter_ids.remove(voter_id)
    
    # Remove from email map if present
    if voter_id in voter_email_map:
        del voter_email_map[voter_id]
    
    # Remove any ballots from this voter
    ballots = [b for b in document["ballots"] if b.get("voter_id") != voter_id]
    
    # Update the database
    result = await db.update_one(
        {"_id": ObjectId(poll_id)}, 
        {"$set": {
            "voter_ids": voter_ids,
            "voter_email_map": voter_email_map,
            "ballots": ballots
        }}
    )
    
    if result.modified_count > 0:
        return {"success": "Voter deleted."}
    else:
        return {"error": "Failed to delete voter."}    


async def regenerate_voter_link(poll_id: str, voter_id: str, owner_id: str, background_tasks: BackgroundTasks):
    """Generate a new voter ID for an existing voter."""
    if not ObjectId.is_valid(poll_id):
        return {"error": "Invalid poll ID."}
    
    document = await db.find_one({"_id": ObjectId(poll_id)})
    
    if document is None:
        return {"error": "Poll not found."}
    
    if document["owner_id"] != owner_id:
        return {"error": "Not authorized."}
    
    if not document.get("is_private", False):
        return {"error": "Can only manage voters in private polls."}
    
    voter_ids = document.get("voter_ids", [])
    voter_email_map = document.get("voter_email_map", {})
    
    if voter_id not in voter_ids:
        return {"error": "Voter not found."}
    
    # Generate new voter ID
    new_voter_id = generate_voter_ids(1)[0]
    
    # Get the email for this voter
    email = voter_email_map.get(voter_id)
    
    # Replace old ID with new ID in voter_ids list
    voter_ids[voter_ids.index(voter_id)] = new_voter_id
    
    # Update email map if email exists
    if email and voter_id in voter_email_map:
        del voter_email_map[voter_id]
        voter_email_map[new_voter_id] = email
    
    # Update any existing ballot to use the new voter_id
    ballots = document["ballots"]
    for ballot in ballots:
        if ballot.get("voter_id") == voter_id:
            ballot["voter_id"] = new_voter_id
    
    # Update the database
    result = await db.update_one(
        {"_id": ObjectId(poll_id)}, 
        {"$set": {
            "voter_ids": voter_ids,
            "voter_email_map": voter_email_map,
            "ballots": ballots
        }}
    )
    
    if result.modified_count > 0:
        # Send email with new link
        if email and not SKIP_EMAILS:
            link = f"https://stablevoting.org/vote/{poll_id}?vid={new_voter_id}"
            
            background_tasks.add_task(
                send_email,
                to_email=email,
                subject=f"New voting link for: {document['title']}",
                html_body=f"""<p>A new voting link has been generated for you.</p>
                <p>Poll: {document['title']}</p>
                <p>Your new voting link: <a href="{link}">{link}</a></p>
                <p>Your previous link has been deactivated.</p>
                <p>You can use this link to vote or update your existing vote.</p>""",
                tag="voter-link-regenerated"
            )
        
        return {
            "success": "New voter link generated.",
            "new_voter_id": new_voter_id,
            "voteUrl": f"https://stablevoting.org/vote/{poll_id}?vid={new_voter_id}"
        }
    else:
        return {"error": "Failed to generate new link."}


async def delete_all_ballots(id, owner_id):
    """Delete all ballots from a poll."""
    if not ObjectId.is_valid(id):
        return {"error": "Invalid poll ID."}
    
    document = await db.find_one({"_id": ObjectId(id)})
    
    if document is None:
        return {"error": "Poll not found."}
    
    if document["owner_id"] != owner_id:
        return {"error": "You do not have permission to delete ballots from this poll."}
    
    # Check if poll is closed or completed
    if document.get("is_completed", False):
        return {"error": "Cannot delete ballots from a completed poll."}
    
    if poll_closed(document.get("closing_datetime", None), document.get("timezone", None)):
        return {"error": "Cannot delete ballots from a closed poll."}
    
    # Get the number of ballots to be deleted for the response
    num_ballots = len(document.get("ballots", []))
    
    if num_ballots == 0:
        return {"error": "No ballots to delete."}
    
    # Delete all ballots
    result = await db.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"ballots": []}}
    )
    
    if result.modified_count > 0:
        return {"success": f"Successfully deleted {num_ballots} ballot(s)."}
    else:
        return {"error": "Failed to delete ballots."}

async def submit_ballot(ballot, id, vid, allow_multiple_vote_pwd):
    """Submit a ballot to the poll."""

    if not ObjectId.is_valid(id):
        return {"error": "Poll not found."}
    document = await db.find_one({"_id": ObjectId(id)})
    if document is None: # poll not found
        return {"error": "Poll not found."}

    # do not accept votes once the poll is completed or its closing time has passed
    if document.get("is_completed", False) or poll_closed(
            document.get("closing_datetime", None), document.get("timezone", None)):
        return {"error": "The poll is no longer accepting votes."}

    # only candidates that belong to the poll may be ranked; a ballot ranking an
    # unknown candidate would otherwise crash the results and rankings pages
    candidates = set(document.get("candidates", []))
    if not set(ballot.ranking.keys()).issubset(candidates):
        return {"error": "The ballot ranks a candidate that is not in the poll."}

    allow_multiple_votes = document.get("allow_multiple_votes", False) or _multiple_vote_allowed(allow_multiple_vote_pwd)

    b = ballot.model_dump()
    if vid is not None:
        b["voter_id"] = vid

    if document["is_private"]:
        if vid is None or vid not in document["voter_ids"]:
            return {"error": "The poll is private."}
        # atomically replace this voter's existing ballot, if there is one
        result = await db.update_one(
            {"_id": ObjectId(id), "ballots.voter_id": vid},
            {"$set": {"ballots.$": b}})
        if result.matched_count > 0:
            return {"success": "Ballot submitted."}
    elif not allow_multiple_votes and ballot.ip not in (None, "n/a"):
        # atomically append only if no ballot with this ip exists yet
        result = await db.update_one(
            {"_id": ObjectId(id), "ballots.ip": {"$ne": ballot.ip}},
            {"$push": {"ballots": b}})
        if result.matched_count == 0:
            return {"error": "Already submitted a ballot."}
        return {"success": "Ballot submitted."}

    await db.update_one({"_id": ObjectId(id)}, {"$push": {"ballots": b}})
    return {"success": "Ballot submitted."}


async def delete_ballot(id, vid):
    """Given a voter id, delete a ballot from the poll"""
    if not ObjectId.is_valid(id):
        return {"error": "Poll not found."}
    document = await db.find_one({"_id": ObjectId(id)})
    if document is None: # poll not found
        return {"error": "Poll not found."}
    if not document["is_private"]:
        return {"error": "Can only delete ballots in private polls."}
    if vid is None or vid not in document["voter_ids"]:
        return {"error": "Voter id not found, cannot delete the ballot."}
    result = await db.update_one(
        {"_id": ObjectId(id)}, {"$pull": {"ballots": {"voter_id": vid}}})
    if result.modified_count > 0:
        return {"success": "Ballot deleted."}
    return {"error": "Ballot not found."}


async def add_rankings(id, owner_id, csv_file, overwrite):
    """add rankings to a poll from a csv file."""
    if not ObjectId.is_valid(id):
        return {"error": "Poll not found."}
    document = await db.find_one({"_id": ObjectId(id)})
    if document is None: # poll not found
        return {"error": "Poll not found."}
    if owner_id != document["owner_id"]:
        return {"error": "Only the poll creater can add rankings to a poll."}

    candidates = document["candidates"]
    num_cands = len(candidates)

    # parse the upload in memory: no temp file to write, leak, or traverse
    csvfile = io.TextIOWrapper(csv_file.file, encoding="utf-8", errors="replace")
    ranking_reader = csv.reader(csvfile, delimiter=',')
    try:
        _cands = next(ranking_reader)
    except StopIteration:
        return {"error": "The file is empty."}
    cands = [c.strip() for c in _cands]
    if not sorted(candidates) == sorted(cands[0:num_cands]):
        return {"error": "The candidates in the file do not match the candidates in the poll."}

    new_ballots = list()
    rowidx = 0
    try:
        for rowidx, row in enumerate(ranking_reader):
            if len([v for v in row if v.strip() != '']) == 0:
                continue
            num_ballot = int(row[num_cands]) if len(row) > num_cands and row[num_cands] != '' and row[num_cands].isdigit() else 1
            for nb in range(num_ballot):
                new_ballots += [{
                    "ranking": {c:int(r) for c,r in zip(cands, row[0:num_cands]) if r.strip() != ''},
                    "voter_id": f"bulk{rowidx}_{nb+1}",
                    "submission_date": None,
                    "ip": csv_file.filename
                }]
    except ValueError:
        return {"error": f"Row {rowidx + 2} of the file contains a rank that is not a number."}

    if overwrite:
        await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": new_ballots}})
        success_message = f"Replaced all the ballots with {len(new_ballots)} ballots in the poll: {document['title']}."
    else:
        await db.update_one( {"_id": ObjectId(id)}, {"$push": {"ballots": {"$each": new_ballots}}})
        success_message = f"Added {len(new_ballots)} ballots to the poll: {document['title']}."
    return {"success": success_message}


###
#
# Voting 
#
###

def poll_closed(dt, tz): 
    if dt is not None:
        closing_dt = arrow.get(dt).to(tz)
    else:
        closing_dt = None
    return closing_dt < arrow.utcnow().to(tz) if closing_dt is not None else False


def dt_string(dt, tz):
    if dt is not None:
        closing_dt = arrow.get(dt).to(tz)
    else:
        closing_dt = None
    return closing_dt.format('MMMM D YYYY @ HH:mm A (ZZZ)') if closing_dt is not None else "N/A"

    
def can_view_outcome(dt, tz, is_completed, can_view_outcome_before_closing, show_outcome, is_owner, is_voter):
    '''
    An outcome can be viewed when either
    1. the person is an owner, or
    2. the person is a voter and the owner enabled show outcome and either the poll is closed or completed or the viewing the outcome before the poll closes is enabled. 
    '''
    if dt is not None:
        closing_dt = arrow.get(dt).to(tz)
    else:
        closing_dt = None
    is_closed =  closing_dt < arrow.utcnow().to(tz) if closing_dt is not None else False

    return is_owner or (is_voter and show_outcome and (closing_dt is None or is_closed or is_completed or (not is_closed and can_view_outcome_before_closing)))

        
def can_vote(vid, is_completed, is_private, voter_ids, dt, tz):
    return not is_completed and not poll_closed(dt, tz) and (not is_private or (vid in voter_ids))

    
def voter_type(poll_data, vid, oid = None): 

    is_owner = oid == poll_data.get("owner_id", False)

    is_voter = not poll_data.get("is_private", False) or (poll_data.get("is_private", False) and vid in poll_data.get("voter_ids", []))

    return is_voter, is_owner


async def poll_ranking_information(id, vid, allowmultiplevote):

    def not_found_response():
        return {
            "error": "Poll not found.",
            "poll_found": False,
            "title": "N/A",
            "allow_multiple_vote": _multiple_vote_allowed(allowmultiplevote),
            "hide_description": False,
            "closing_datetime": "n/a",
            "timezone": "n/a",
            "is_closed": True,
            "is_completed": True,
            "can_vote": False,
            "can_view_outcome": False
            }

    if not ObjectId.is_valid(id):
        return not_found_response()

    document = await db.find_one({"_id": ObjectId(id)})

    if document is None: # poll not found
        return not_found_response()

    allow_multiple_vote = document.get("allow_multiple_votes", False) or _multiple_vote_allowed(allowmultiplevote)

    # vid could either be a voter id or the owner id
    is_voter, is_owner = voter_type(document, vid, vid)
    
    is_closed = poll_closed( 
                document.get("closing_datetime", None), 
                document.get("timezone", None))
    
    is_completed = document.get("is_completed", False) or is_closed
    is_private = document.get("is_private", False)
    
    closing_dt = document.get("closing_datetime", None)
    tz = document.get("timezone", None)
    if closing_dt is not None:
        dt = arrow.get(closing_dt).to(tz)
        now = arrow.utcnow().to(tz)
        time_remaining_str = f'The poll closes in {humanize.precisedelta(dt - now, suppress=["seconds"], minimum_unit="minutes")}'
    else:
        time_remaining_str = None
    print(time_remaining_str)
    v_can_vote = can_vote(
                vid,
                is_completed,
                is_private,
                document.get("voter_ids",[]),
                closing_dt, 
                tz)
    
    v_can_view_outcome = can_view_outcome(
                closing_dt, 
                tz, 
                is_completed,
                document.get("can_view_outcome_before_closing", False), 
                document.get("show_outcome", False),
                is_owner,
                is_voter)
    
    resp = {
        "title": document.get("title", ""),
        "description": document.get("description", ""),
        "hide_description": document.get("hide_description", False),
        "candidates": document.get("candidates", []),
        "allow_multiple_vote": allow_multiple_vote,
        "is_private": document.get("is_private", False),
        "ranking": {},
        "closing_datetime_str": dt_string(document.get("closing_datetime", None), document.get("timezone", None)),
        "timezone": document.get("timezone", "n/a"),
        "time_remaining_str": time_remaining_str,
        "is_closed": is_closed,
        "is_completed": is_completed,
        "can_vote": v_can_vote,
        "can_view_outcome": v_can_view_outcome
        }
    print("poll_ranking_information: resp", resp)
    if document["is_private"] and (vid is not None and vid in document["voter_ids"]): 
        for b in document["ballots"]: 
            if b["voter_id"] == vid: 
                resp["ranking"] = b["ranking"]
    return resp


async def submitted_ranking_information(id, owner_id):

    if not ObjectId.is_valid(id):
        return {"error": "Poll not found."}

    document = await db.find_one({"_id": ObjectId(id)})

    if document is None: # poll not found
        return {"error": "Poll not found."}
    else:
        is_voter, is_owner = voter_type(document, owner_id, owner_id)

        if not is_owner: 
            print("Not a owner.")
            return {"error": "You must be the owner to view the ranking data."}
        
        unranked_candidates = [c for c in document["candidates"] if all([c not in b["ranking"].keys() for b in document["ballots"]])]
        
        num_empty_ballots = len([b for b in document["ballots"] if all([c not in b["ranking"].keys() for c in document["candidates"]])])
        cand_to_cidx = {c: str(i) for i, c in enumerate(document["candidates"])}
        cmap = {str(cidx):c for c,cidx in cand_to_cidx.items()}

        resp = {
            "unranked_candidates": unranked_candidates,
            "num_empty_ballots": num_empty_ballots, 
            "num_voters": 0,
            "num_rows": 0,
            "columns": [[]],
            "csv_data": [[]],
            "cmap": cmap,
        }

        if len(document["ballots"]) > 0:

            prof = ProfileWithTies([{cand_to_cidx[c]: rank 
                                     for c,rank in r["ranking"].items()} 
                                     for r in document["ballots"]])
            prof.display()
            num_voters = prof.num_voters
            print(num_voters)
            columns, num_rows = generate_columns_from_profiles(prof)
            resp["num_voters"] = num_voters
            resp["num_rows"] = num_rows
            resp["columns"] = columns
            resp["csv_data"] = generate_csv_data(prof, cmap)
    return resp


async def poll_outcome(id, owner_id, voter_id):
    print("Generating poll outcome for ", id)
    print("Owner id ", owner_id)
    print("Voter id ", voter_id)
    if not ObjectId.is_valid(id): 
        return {"error": "Poll not found."}
    print("Getting document...")
    document = await db.find_one({"_id": ObjectId(id)}) 
    print("got document")
    print(document)
    error_message = ''
    if document is None: # poll not found
        print("Poll not found.")
        return {"error": "Poll not found."}
    else: 
        cand_to_cidx = {c: str(i) for i, c in enumerate(document["candidates"])}
        cmap = {str(cidx):c for c,cidx in cand_to_cidx.items()}

        is_voter, is_owner = voter_type(document, voter_id, owner_id)

        can_view = can_view_outcome(
                document.get("closing_datetime", None), 
                document.get("timezone", None), 
                document.get("is_completed", None), 
                document.get("can_view_outcome_before_closing", False), 
                document.get("show_outcome", True), 
                is_owner,
                is_voter)
        
        print("is_completed", document.get("is_completed", None))
        print("can_view ", can_view)
        title = str(document["title"])
        print("title", title)
        print(document)
        closing_datetime =  dt_string(document.get("closing_datetime", None), document.get("timezone", None))
        timezone = document.get("timezone") or "N/A"
        is_closed = poll_closed(document.get("closing_datetime", None), document.get("timezone", None))
        print("is closed", is_closed)
        print(document.get("is_completed", False))
        print(document.get("result", None))
        print(document.get("is_completed", False) and document.get("result", None) is not None)

        if document.get("is_completed", False) and document.get("result", None) is not None: 
            """The poll is completed and there is a saved result."""
            result = document["result"]
        else: # otherwise generate the result.    
            show_rankings = document["show_rankings"] 
            margins= {}
            num_voters = 0
            sv_winners = []
            sc_winners = []
            condorcet_winner = "N/A"
            defeat_relation = {}
            explanations = {}
            prof_is_linear = False
            linear_order = []
            splitting_numbers = {}
            num_rows = 0
            columns = [[]]
            if can_view and len(document["ballots"]) > 0:

                prof = ProfileWithTies([{cand_to_cidx[c]: rank 
                                         for c,rank in r["ranking"].items()} 
                                         for r in document["ballots"]])
                prof.display()

                if not any([len(list(r.rmap.keys())) > 0 for r in prof.rankings]):
                    error_message = "No candidates are ranked."
                else: 
                    margins = {c1: {c2: prof.margin(c1, c2) for c2 in prof.candidates} for c1 in prof.candidates}
                    condorcet_winner = prof.condorcet_winner()

                    try:
                        sc_defeat = func_timeout(2, split_cycle_defeat, args=(prof,), kwargs=None)
                        sc_winners = [str(c) for c in prof.candidates if not any([c2 for c2 in prof.candidates if sc_defeat.has_edge(c2,c)])]
                        defeat_relation = {str(c): {str(c2): sc_defeat.has_edge(c,c2) for c2 in prof.candidates} for c in prof.candidates }
                    except FunctionTimedOut:
                        sc_defeat = dict()
                        sc_winners = split_cycle(prof)
                        defeat_relation = {str(c): {} for c in prof.candidates }

                    try:
                        sv_winners, _, explanations = func_timeout(2, stable_voting_with_explanations_, args=(prof,), kwargs = {"curr_cands": None, "mem_sv_winners": {}, "explanations": {}})
                    except FunctionTimedOut:
                        sv_winners = stable_voting(prof)
                        explanations = dict()

                    num_voters = prof.num_voters
                    prof_is_linear, linear_order = is_linear(prof)
                    columns, num_rows = generate_columns_from_profiles(prof)
                    if condorcet_winner is None: 
                        try:
                            splitting_numbers = func_timeout(2, get_splitting_numbers, args=(prof,), kwargs=None)
                        except FunctionTimedOut:
                            splitting_numbers = {}
                    else: 
                        splitting_numbers = {}

            result = {
                "margins": margins, 
                "num_voters": str(num_voters),
                "cmap": cmap,
                "show_rankings": show_rankings, 
                "sv_winners": sv_winners, 
                "sc_winners": sc_winners, 
                "selected_sv_winner": None, # only set if the poll is completed
                "condorcet_winner": condorcet_winner, 
                "explanations": explanations,
                "defeats": defeat_relation,
                "splitting_numbers": splitting_numbers,
                "prof_is_linear": prof_is_linear,
                "linear_order": linear_order if prof_is_linear else [],
                "num_rows": num_rows,
                "columns":columns,
                }

            if is_closed or document.get("is_completed", False):
                # close the poll and save the result (including the selected winner if there is a tie)
                if len(sv_winners) > 1:
                    selected_sv_winner = random.choice(sv_winners)
                    result["selected_sv_winner"] = selected_sv_winner

                await db.update_one( {"_id": ObjectId(id)}, {"$set": {"result": result, "is_completed": True}})
            else:
                # the poll is still open, so remove any saved result
                await db.update_one( {"_id": ObjectId(id)}, {"$set": {"result": None}})

    result["title"] = title
    result["is_closed"] = is_closed
    result["is_completed"] = document.get("is_completed", False) or is_closed
    result["can_view"] = can_view
    result["closing_datetime"] = closing_datetime
    result["timezone"] = timezone
    result["election_id"] = str(id)
    
    if error_message != '':
        result["error"] = error_message
    return result


async def demo_poll_outcome(rankings):

    print("Generating poll outcome for ", rankings)

    closing_datetime = None
    timezone = "N/A"
    is_closed = False
    show_rankings = True 
    margins= {}
    num_voters = 0

    ballots = list()
    for r in rankings: 
        print(r)
        for n in range(int(r["num"])): 
            ballots.append(r["ranking"])
    _prof = ProfileWithTies([r for r in ballots])
    _prof.display()
    curr_rankings, counts = _prof.rankings_as_dicts_counts
    cand_to_cindex = {str(c): i for i,c in enumerate(_prof.candidates)}
    cmap = {cindx: str(c) for c, cindx in cand_to_cindex.items()}

    prof = ProfileWithTies([{cand_to_cindex[c]: r 
                             for c, r in rank.items()} 
                             for rank in curr_rankings], rcounts=counts)
    
    prof.display()
    print(cmap)
    num_ranked_cands = len(list(set([_c  for _r in prof.rankings for _c in _r.rmap.keys()])))
    if num_ranked_cands == 0: #not any([len(list(r.rmap.keys())) > 0 for r in prof.rankings]):
        columns, num_rows = generate_columns_from_profiles(prof)
        result = {
            "no_candidates_ranked": True,
            "margins": {}, 
            "num_voters": str(prof.num_voters),
            "show_rankings": show_rankings, 
            "sv_winners": list(), 
            "sc_winners": list(), 
            "selected_sv_winner": None, # only set if the poll is completed
            "condorcet_winner": None, 
            "explanations": {},
            "defeats": {},
            "splitting_numbers": {},
            "prof_is_linear": False,
            "linear_order": list(),
            "num_rows": num_rows,
            "columns":columns,
            "cmap": cmap,
        }
    else:
        margins = {c1: {c2: prof.margin(c1, c2) for c2 in prof.candidates} for c1 in prof.candidates}
        condorcet_winner = prof.condorcet_winner()

        try:
            sc_defeat = func_timeout(2, split_cycle_defeat, args=(prof,), kwargs=None)
            sc_winners = [str(c) for c in prof.candidates if not any([c2 for c2 in prof.candidates if sc_defeat.has_edge(c2,c)])]
            defeat_relation = {str(c): {str(c2): sc_defeat.has_edge(c,c2) for c2 in prof.candidates} for c in prof.candidates }
        except FunctionTimedOut:
            sc_defeat = dict()
            sc_winners = split_cycle(prof)
            defeat_relation = {str(c): {} for c in prof.candidates }

        try:
            sv_winners, _, explanations = func_timeout(2, stable_voting_with_explanations_, args=(prof,), kwargs = {"curr_cands": None, "mem_sv_winners": {}, "explanations": {}})
        except FunctionTimedOut:
            sv_winners = stable_voting(prof)
            explanations = dict()

        num_voters = prof.num_voters
        prof_is_linear, linear_order = is_linear(prof)
        columns, num_rows = generate_columns_from_profiles(prof)
        if condorcet_winner is None: 
            try:
                splitting_numbers = func_timeout(2, get_splitting_numbers, args=(prof,), kwargs=None)
            except FunctionTimedOut:
                splitting_numbers = {}
                        #splitting_numbers = get_splitting_numbers(prof)
        else: 
            splitting_numbers = {}

        result = {
            "margins": margins, 
            "num_voters": str(num_voters),
            "show_rankings": show_rankings, 
            "sv_winners": sv_winners, 
            "sc_winners": sc_winners, 
            "selected_sv_winner": None, # only set if the poll is completed
            "condorcet_winner": condorcet_winner, 
            "explanations": explanations,
            "defeats": defeat_relation,
            "splitting_numbers": splitting_numbers,
            "prof_is_linear": prof_is_linear,
            "linear_order": linear_order if prof_is_linear else [],
            "num_rows": num_rows,
            "columns":columns,
            "cmap": cmap,
            }
        if len(sv_winners) > 1: 
            selected_sv_winner = random.choice(sv_winners)
            result["selected_sv_winner"] = selected_sv_winner

    if num_ranked_cands == 1: 
        result["one_ranked_candidate"] = True
    result["title"] = "Demo Poll"
    result["is_closed"] = is_closed 
    result["is_completed"] = False
    result["can_view"] = True
    result["closing_datetime"] = closing_datetime
    result["timezone"] = timezone
    result["election_id"] = "demo_poll"

    result['sv_winners'] = [str(w) for w in result.get('sv_winners', [])]
    if 'sc_winners' in result:
        # if you want to enforce them too
        result['sc_winners'] = [str(w) for w in result['sc_winners']]
    if 'condorcet_winner' in result and result['condorcet_winner'] is not None:
        result['condorcet_winner'] = str(result['condorcet_winner'])
    if 'linear_order' in result:
        result['linear_order'] = [str(w) for w in result['linear_order']]


    print("result ", result)
    return result


async def resend_voter_email(poll_id: str, voter_email: str, owner_id: str, background_tasks: BackgroundTasks):
    """Resend invitation email to a voter with a new voting link."""
    if not ObjectId.is_valid(poll_id):
        return {"error": "Invalid poll ID."}
    
    document = await db.find_one({"_id": ObjectId(poll_id)})
    
    if document is None:
        return {"error": "Poll not found."}
    
    if document["owner_id"] != owner_id:
        return {"error": "Not authorized."}
    
    if not document.get("is_private", False):
        return {"error": "Can only manage voters in private polls."}
    
    voter_email_map = document.get("voter_email_map", {})
    email_send_counts = document.get("email_send_counts", {})
    
    # Find the voter_id for this email
    voter_id = None
    for vid, email in voter_email_map.items():
        if email == voter_email:
            voter_id = vid
            break
    
    if not voter_id:
        return {"error": "Voter email not found."}
    
    # Generate new voter ID
    new_voter_id = generate_voter_ids(1)[0]
    
    # Get voter_ids list
    voter_ids = document.get("voter_ids", [])
    
    # Replace old ID with new ID in voter_ids list
    if voter_id in voter_ids:
        voter_ids[voter_ids.index(voter_id)] = new_voter_id
    
    # Update email map
    del voter_email_map[voter_id]
    voter_email_map[new_voter_id] = voter_email
    
    # Update any existing ballot to use the new voter_id
    ballots = document["ballots"]
    for ballot in ballots:
        if ballot.get("voter_id") == voter_id:
            ballot["voter_id"] = new_voter_id
    
    # Increment email send count
    email_send_counts[voter_email] = email_send_counts.get(voter_email, 1) + 1
    
    # Update the database
    result = await db.update_one(
        {"_id": ObjectId(poll_id)}, 
        {"$set": {
            "voter_ids": voter_ids,
            "voter_email_map": voter_email_map,
            "email_send_counts": email_send_counts,
            "ballots": ballots
        }}
    )
    
    if result.modified_count > 0:
        # Send email with new link
        if not SKIP_EMAILS:
            link = f"https://stablevoting.org/vote/{poll_id}?vid={new_voter_id}"
            
            background_tasks.add_task(
                send_email,
                to_email=voter_email,
                subject=f"Reminder: Participate in the poll - {document['title']}",
                html_body=f"""<p>This is a reminder to participate in the poll.</p>
                <p>Poll: {document['title']}</p>
                <p>Description: {document.get('description', '')}</p>
                <p>Your voting link: <a href="{link}">{link}</a></p>
                <p>Note: This new link replaces any previous links sent to you.</p>""",
                tag="voter-invitation-resend"
            )
        
        return {
            "success": f"Email resent to {voter_email}. Total emails sent: {email_send_counts[voter_email]}"
        }
    else:
        return {"error": "Failed to resend email."}