#
# Functions to manage polls
#

from fastapi import APIRouter, HTTPException, BackgroundTasks, File, UploadFile
from fastapi_mail import FastMail, MessageSchema,ConnectionConfig
import arrow
import random
import motor.motor_asyncio
from pymongo import read_concern
import uuid
import csv
import os
from bson import ObjectId

from pref_voting.profiles_with_ties import ProfileWithTies
from pref_voting.voting_methods import split_cycle_defeat
from polls.models import CreatePoll, UpdatePoll
from polls.helpers import generate_voter_ids, participate_email
from polls.voting import is_linear, generate_columns_from_profiles, stable_voting_with_explanations_

SKIP_EMAILS = True

#mongo_details = 'mongodb://127.0.0.1:27017'
mongo_details = os.getenv('MONGO_DETAILS')
client = motor.motor_asyncio.AsyncIOMotorClient(mongo_details)


db = client.StableVoting2.Polls_test

email_username = os.getenv('EMAIL_USERNAME')
email_pass = os.getenv('EMAIL_PASS')

conf = ConnectionConfig(
    MAIL_USERNAME = email_username,
    MAIL_PASSWORD = email_pass,
    MAIL_FROM = "stablevoting.org@gmail.com",
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_FROM_NAME = "Stable Voting",
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

async def create_poll(background_tasks: BackgroundTasks, poll_data: CreatePoll):
    """Create a poll."""
    print("creating a poll...")
    now = arrow.now()
    print(now.format('YYYY-MM-DD HH:mm'))
    voter_ids = []
    if poll_data.is_private: 
        voter_ids = generate_voter_ids(len(poll_data.voter_emails))
    owner_id = generate_voter_ids(1)[0]
    poll = {
        "title": poll_data.title,
        "description": poll_data.description,
        "candidates": poll_data.candidates,
        "is_private": poll_data.is_private,
        "voter_ids": voter_ids,
        "owner_id": owner_id,
        "show_rankings": poll_data.show_rankings,
        "closing_datetime": poll_data.closing_datetime,
        "timezone": poll_data.timezone,
        "can_view_outcome_before_closing": poll_data.can_view_outcome_before_closing,
        "show_outcome": poll_data.show_outcome,
        "ballots": [],
        "is_completed": False,
        "result": None,
        "creation_dt": now.format('MMMM DD, YYYY @ HH:mm')
    }
    result = await db.insert_one(poll)

    if not SKIP_EMAILS:
        message = MessageSchema(
            subject=f"New Poll Created",
            recipients= ["stablevoting.org@gmail.com", "epacuit@gmail.com"],
            html = f"""<p>Poll Created: https://stablevoting.org/results/{result.inserted_id}?oid={owner_id}</p>
            <p></p>
            <p>admin: https://stablevoting.org/admin/{result.inserted_id}?oid={owner_id}</p><p></p><p>{poll}</p>""",
            subtype='html'
        )
        fm = FastMail(conf)
        background_tasks.add_task(fm.send_message, message)

        for em,voter_id in zip(poll_data.voter_emails, voter_ids):
            print("sending email to ", em)
            link = f"https://stablevoting.org/vote/{result.inserted_id}/{voter_id}"
            print(participate_email(poll_data.title, poll_data.description, link))
            message = MessageSchema(
                subject=f"Participate in the poll: {poll_data.title}",
                recipients= [em],
                html = participate_email(poll_data.title, poll_data.description, link),
                subtype='html'
                )
            fm = FastMail(conf)

            background_tasks.add_task(fm.send_message,message)

    return {"id": str(result.inserted_id), "owner_id": owner_id}

async def update_poll(id, owner_id, poll_data: UpdatePoll, background_tasks: BackgroundTasks):
    """Update a poll. """

    print("updating poll ", id)
    document = await db.find_one({"_id": ObjectId(id)}) 
    poll_data = poll_data.dict() 
    if document is None: # poll not found
        return {"error": "Poll not found."}
    else: 
        if owner_id != document["owner_id"]: 
            return {"error": "You do not have permission to modify the poll."}
        
        get_data = lambda field : poll_data[field] if poll_data[field] is not None else  document[field]
        new_voter_ids = []
        if poll_data["is_private"] and len(poll_data["new_voter_emails"]) > 0: 
            new_voter_ids = generate_voter_ids(len(poll_data["new_voter_emails"]))
        
        if poll_data["is_completed"] is not None and poll_data["open_poll"] is not None: 
            print("WARNING...there is somethign wrong.   Receiving poll_data with is_completed and open_poll both non-null.")
                
        new_poll = {
            "title": get_data("title"),
            "description": get_data("description"),
            "is_private": get_data("is_private"),
            "voter_ids": document["voter_ids"] + new_voter_ids,
            "show_rankings": get_data("show_rankings"),
            "closing_datetime": get_data("closing_datetime") if poll_data["closing_datetime"] != "del" else None,
            "timezone": get_data("timezone"),
            "can_view_outcome_before_closing": get_data("can_view_outcome_before_closing"),
            "show_outcome": get_data("show_outcome"),
            "ballots": document["ballots"],
            "is_completed": (poll_data["open_poll"] is not None and not poll_data["open_poll"]) or (poll_data["is_completed"] is not None and poll_data["is_completed"]),
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
        
        #if open_poll: 
        #    result_doc = await db.find_one({"_id": document["result"]}) 

        result = await db.update_one({"_id": ObjectId(id)}, {"$set": new_poll})

        if not SKIP_EMAILS: 
            if len(new_voter_ids) > 0: 
                for em,voter_id in zip(poll_data["new_voter_emails"], new_voter_ids):
                    print("sending email to ", em)
                    link = f"https://stablevoting.org/vote/{id}/{voter_id}"

                    message = MessageSchema(
                        subject=f'Participate in the poll: {new_poll["title"]}',
                        recipients= [em],
                        html = participate_email(poll_data["title"], new_poll["description"], link),
                        subtype='html'
                        )
                    fm = FastMail(conf)

                    background_tasks.add_task(fm.send_message,message)

    return resp

async def delete_poll(id, oid):
    """Delete the poll given the owner id."""
    if len(id) != 24: 
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

async def submit_ballot(ballot, id, vid):
    """Submit a ballot to the poll."""
    read_concern.ReadConcern('linearizable')
    document = await db.find_one({"_id": ObjectId(id)}) 
    if document is None: # poll not found
        return {"error": "Poll not found."}
    else: 
        ballots = document["ballots"]
        if document["is_private"] and (vid is not None and vid in document["voter_ids"]): 
            for bidx, b in enumerate(ballots): 
                if b["voter_id"] == vid: 
                    b = ballot.dict()
                    b["voter_id"] = vid
                    # update
                    ballots[bidx] = b
                    await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": ballots}})
                    return {"success": "Ballot submitted."}
        elif document["is_private"] and (vid is  None or vid not in document["voter_ids"]): 
            return {"error": "The poll is private."}
        elif not document["is_private"]: 
            if ballot.ip != "n/a":
                for b in ballots: 
                    if b["ip"] == ballot.ip:
                        return {"error": "Already submitted a ballot."}
        b = ballot.dict()
        if vid is not None: 
            b["voter_id"] = vid
        ballots.append(b)
        await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": ballots}})
        return {"success": "Ballot submitted."}


async def delete_ballot(id, vid):
    """Given a voter id, delete a ballot from the poll"""
    document = await db.find_one({"_id": ObjectId(id)})  
    if document is None: # poll not found
        return {"error": "Poll not found."}
    else: 
        ballots = document["ballots"]
        if document["is_private"] and (vid is not None and vid in document["voter_ids"]): 
            for bidx, b in enumerate(ballots): 
                if b["voter_id"] == vid: 
                    # update
                    ballots.pop(bidx)
                    await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": ballots}})
                    return {"success": "Ballot deleted."}
        elif document["is_private"] and (vid is  None or vid not in document["voter_ids"]): 
            return {"error": "Voter id not found, cannot delete the ballot."}
        elif not document["is_private"]: 
            return {"error": "Can only delete ballots in private polls."}
        return {"error": "Ballot not found."}

async def add_rankings(id, owner_id, csv_file, overwrite): 
    """add rankings to a poll from a csv file."""
    document = await db.find_one({"_id": ObjectId(id)})  
    if document is None: # poll not found
        return {"error": "Poll not found."}
    else: 
        if owner_id != document["owner_id"]:
            return {"error": "Only the poll creater can add rankings to a poll."}
        else: 
            file_location = f"./tmpcsvfiles/{str(uuid.uuid4())}-{csv_file.filename}"
            print(file_location)
            new_ballots = list()
            with open(file_location, "wb+") as file_object:
                print("Writing file....")
                file_object.write(csv_file.file.read())
            with open(file_location) as csvfile:
                ranking_reader = csv.reader(csvfile, delimiter=',')
                cands = next(ranking_reader)
                if not sorted(document["candidates"]) == sorted(cands):
                    return {"error": "The candidates in the file do not match the candidates in the poll."}
                
                for rowidx, row in enumerate(ranking_reader):
                    new_ballots += [{
                        "ranking": {c:int(r) for c,r in zip(cands, row) if r != ''},
                        "voter_id": f"bulk{rowidx}",
                        "submission_date": None,
                        "ip": csv_file.filename
                    }] 

                print(new_ballots)
                curr_ballots = document["ballots"]
                if overwrite: 
                    await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": new_ballots}})
                    success_message = f"Replaced all the ballots with {len(new_ballots)} ballots in the poll: {document['title']}."
                else: 
                    await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": curr_ballots + new_ballots}})
                    success_message = f"Added {len(new_ballots)} ballots to the poll: {document['title']}."
                os.remove(file_location)
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
    
def can_view_outcome(dt, tz, can_view_outcome_before_closing, show_outcome, is_owner, is_voter):
    '''
    An outcome can be viewed when either
    1. the person is an owner, or
    2. the person is a voter and the owner enabled show outcome and either the poll is closed or the viewing the outcome before the poll closes is enabled. 
    '''
    if dt is not None:
        closing_dt = arrow.get(dt).to(tz)
    else:
        closing_dt = None
    is_closed =  closing_dt < arrow.utcnow().to(tz) if closing_dt is not None else False
    return is_owner or (is_voter and show_outcome and (closing_dt is None or is_closed  or (not is_closed and can_view_outcome_before_closing)))
        
def can_vote(vid, is_private, voter_ids, dt, tz):
    return not poll_closed(dt, tz) and (not is_private or (vid in voter_ids))
    
def voter_type(poll_data, vid, oid = None): 

    is_owner = oid == poll_data.get("owner_id", False)

    is_voter = not poll_data.get("is_private", False) or (poll_data.get("is_private", False) and vid in poll_data.get("voter_ids", []))

    return is_voter, is_owner

def close_poll(id, document, result): 
    """Close the poll."""

def open_poll(id, document, result): 
    """Open the poll."""

async def poll_outcome(id, owner_id, voter_id):

    print("Generating poll outcome for ", id)
    print("Owner id ", owner_id)
    print("Voter id ", voter_id)
    if len(id) != 24: 
        print("Invalid id.")
        return {"error": "Poll not found."}
    
    document = await db.find_one({"_id": ObjectId(id)}) 
    
    error_message = ''
    if document is None: # poll not found
        print("Poll not found.")
        return {"error": "Poll not found."}
    else: 
        is_voter, is_owner = voter_type(document, voter_id, owner_id)
        can_view = can_view_outcome(
                document.get("closing_datetime", None), 
                document.get("timezone", None), 
                document.get("can_view_outcome_before_closing", False), 
                document.get("show_outcome", True), 
                is_owner,
                is_voter)

        title = str(document["title"])

        closing_datetime =  dt_string(document.get("closing_datetime", None), document.get("timezone", None))
        timezone = document["timezone"] if document["timezone"] is not None else "N/A"
        is_closed = poll_closed(document.get("closing_datetime", None), document.get("timezone", None))
        print(document.get("is_completed", False))
        print(document.get("result", None))
        print(document.get("is_completed", False) and document.get("result", None) is not None)
        if document.get("is_completed", False) and document.get("result", None) is not None: 
            """The poll is completed and there is a saves result."""
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
            #splitting_numbers = None
            num_rows = 0
            columns = [[]]
            #if not can_view: 
            #    error_message = "Cannot view the outcome."
            if len(document["ballots"]) > 0:
                prof = ProfileWithTies([r["ranking"] for r in document["ballots"]])
                prof.display()
                if document.get("is_completed", False) and document.get("result", None) is not None: 
                    response = True
                if not any([len(list(r.rmap.keys())) > 0 for r in prof.rankings]):
                    error_message = "No candidates are ranked."
                else: 
                    margins = {c1: {c2: prof.margin(c1, c2) for c2 in prof.candidates} for c1 in prof.candidates}
                    condorcet_winner = prof.condorcet_winner()
                    sc_defeat = split_cycle_defeat(prof)
                    sc_winners = [str(c) for c in prof.candidates if not any([c2 for c2 in prof.candidates if sc_defeat.has_edge(c2,c)])]
                    defeat_relation = {str(c): {str(c2): sc_defeat.has_edge(c,c2) for c2 in prof.candidates} for c in prof.candidates }
                    sv_winners, _, explanations = stable_voting_with_explanations_(prof, curr_cands = None, mem_sv_winners = {}, explanations = {})
                    num_voters = prof.num_voters
                    prof_is_linear, linear_order = is_linear(prof)
                    columns, num_rows = generate_columns_from_profiles(prof)
                    #if cw is None and len(prof.candidates) < 7: 
                    #    splitting_numbers = get_splitting_numbers(prof)
                    #else: 
                    #    splitting_numbers = {}
            #else: 
            #    error_message = "No ballots submitted."
            #print(timezone)
            result = {
                "margins": margins, 
                "num_voters": str(num_voters),
                "show_rankings": show_rankings, 
                "sv_winners": sv_winners, 
                "sc_winners": sc_winners, 
                "condorcet_winner": condorcet_winner, 
                "explanations": explanations,
                "defeats": defeat_relation,
                #"splitting_numbers": splitting_numbers,
                "prof_is_linear": prof_is_linear,
                "linear_order": linear_order if prof_is_linear else [],
                "num_rows": num_rows,
                "columns":columns
                }

            if is_closed or document.get("is_completed", False): 
                # close the poll
                if len(sv_winners) > 1: 
                    selected_sv_winner = random.choice(sv_winners)
                result["selected_sv_winner"] = selected_sv_winner
                await db.update_one( {"_id": ObjectId(id)}, {"$set": {"result": result, "is_completed": True}})

            if not document.get("is_completed", False): 
                # remove the saved result
                await db.update_one( {"_id": ObjectId(id)}, {"$set": {"result": None}})

    result["title"] = title
    result["is_closed"] = is_closed or document['is_completed']
    result["can_view"] = can_view
    result["closing_datetime"] = closing_datetime
    result["timezone"] = timezone
    result["election_id"] = str(id)
    
    if error_message != '':
        result["error"] = error_message
    return result

