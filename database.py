import motor.motor_asyncio
from fastapi import BackgroundTasks
from pymongo import MongoClient, read_concern
from model import CreatePoll, UpdatePoll
from voting.profiles_with_ties import ProfileWithTies
from voting.stable_voting import *
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from bson import ObjectId
import random
import uuid
import os
import arrow
import csv
from pref_voting.voting_methods import stable_voting_faster
from func_timeout import func_timeout, FunctionTimedOut



client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv('MONGO_DETAILS'))

#
db = client.StableVoting.Polls

conf = ConnectionConfig(
    MAIL_USERNAME = "stablevoting.org@gmail.com",
    MAIL_PASSWORD = os.getenv('EMAIL_PWD'),
    MAIL_FROM = "stablevoting.org@gmail.com",
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp-relay.sendinblue.com",
    MAIL_FROM_NAME="Stable Voting",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    #MAIL_TLS=True,
    #MAIL_SSL=False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

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
    print("is_closed", is_closed)
    return is_owner or (is_voter and show_outcome and (closing_dt is None or is_closed  or (not is_closed and can_view_outcome_before_closing)))
        
def can_vote(vid, is_private, voter_ids, dt, tz):
    return not poll_closed(dt, tz) and (not is_private or (vid in voter_ids))
    
def voter_type(poll_data, vid, oid = None): 

    is_owner = oid == poll_data.get("owner_id", False)

    is_voter = not poll_data.get("is_private", False) or ((poll_data.get("is_private", False) and vid in poll_data.get("voter_ids", [])))
    return is_voter, is_owner

def participate_email(poll_title, poll_description, url): 
    return  f'''<html><body>
<p>Hello from Stable Voting,</p>

<p>You have been invited to participate in the poll:</p>

<p>{poll_title}</p>

{"<p>" + poll_description + "</p>" if poll_description is not None else ""}

<p>Use the following link to vote in the poll: </p>

<a href="{url}">{url}</a>

<br/>
<br/>

<p><a href="https://stablevoting.org/about">Learn more about Stable Voting</a></p>

</body></html>'''


def generate_voter_ids(num_voters): 
    '''generate num_voters unique ids'''
    
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    ids =   [''.join(random.choices(alphabet, k=8)) for _ in range(num_voters)]

    while len(ids) != len(list(set(ids))): 
        ids =  [''.join(random.choices(alphabet, k=8)) for _ in range(num_voters)]
    return ids

async def create_poll(background_tasks: BackgroundTasks, poll_data: CreatePoll):
    print("creating a poll...")

    now = arrow.now()
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
        "result_id": None,
        "creation_dt": now.format('MMMM DD, YYYY @ HH:mm')
    }
    result = await db.insert_one(poll)

    message = MessageSchema(
        subject=f"New Poll Created",
        recipients= ["stablevoting.org@gmail.com", "epacuit@gmail.com"],
        body = f"""<p>Poll Created: https://stablevoting.org/vote/{result.inserted_id}?oid={owner_id}</p><p></p><p>{poll}</p>""",
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    await fm.send_message(message)

    fm = FastMail(conf)
    background_tasks.add_task(fm.send_message, message)

    for em,voter_id in zip(poll_data.voter_emails, voter_ids):
        print("sending email to ", em)
        link = f"https://stablevoting.org/vote/{result.inserted_id}?vid={voter_id}"
        print(participate_email(poll_data.title, poll_data.description, link))
        message = MessageSchema(
            subject=f"Participate in the poll: {poll_data.title}",
            recipients= [em],
            body = participate_email(poll_data.title, poll_data.description, link),
            subtype=MessageType.html
             )
        fm = FastMail(conf)

        background_tasks.add_task(fm.send_message,message)

    return {"id": str(result.inserted_id), "owner_id": owner_id}

async def send_email(message, background_tasks, vid=None, oid=None): 

        message = MessageSchema(
            subject=f"Contact form message",
            recipients= ["stablevoting.org@gmail.com"],
            body = f"""<p>Name: {message.name}</p><p>Email: {message.email} </p><p>Message: {message.message}</p>""",
            subtype=MessageType.html
             )
        fm = FastMail(conf)

        background_tasks.add_task(fm.send_message,message)

        return {"success": "Message sent to stablevoting.org@gmail.com."}

async def send_vote_emails(emails_data, id, background_tasks, oid=None): 

    
    for em in emails_data.emails:
        message = MessageSchema(
            subject=f"Participate in the poll: {emails_data.title}",
            recipients= [em],
            body = participate_email(emails_data.title, emails_data.description, emails_data.link),
            subtype=MessageType.html
             )
        fm = FastMail(conf)

        background_tasks.add_task(fm.send_message,message)

    return {"success": "Emails sent."}

async def poll_data(id, oid): 
    document = await db.find_one({"_id": ObjectId(id)})  

    if document is None: # poll not found
        resp = {"error": "Poll not found."}
    else: 
        is_closed = poll_closed( 
                    document.get("closing_datetime", None), 
                    document.get("timezone", None))

        is_owner = document["owner_id"] == oid
        un_ranked = [c for c in document["candidates"] if all([c not in b["ranking"].keys() for b in document["ballots"]])]
        num_no_ranked_cands = len([b for b in document["ballots"] if all([c not in b["ranking"].keys() for c in document["candidates"]])])
# vid could either be a voter id or the owner id
        
        is_closed = poll_closed( 
                    document.get("closing_datetime", None), 
                    document.get("timezone", None))
        v_can_view_outcome = can_view_outcome(
                    document.get("closing_datetime", None), 
                    document.get("timezone", None), 
                    document.get("can_view_outcome_before_closing", False), 
                    document.get("show_outcome", False),
                    is_owner,
                    True)
        resp = {
            "is_owner": is_owner,
            "title": document.get("title", "n/a"),
            "description": document.get("description", "n/a"),
            "candidates": document.get("candidates", []),
            "is_private": document.get("is_private", False),
            "num_voters": len(document.get("voter_ids", [])),
            "show_rankings": document.get("show_rankings", True),
            "closing_datetime": document.get("closing_datetime", ""),
            "timezone": document.get("timezone", ""),
            "can_view_outcome_before_closing": document.get("can_view_outcome_before_closing", True),
            "can_view_outcome": v_can_view_outcome,
            "show_outcome": document.get("show_outcome", True),
            "num_ballots": len(document["ballots"]),
            "unranked_candidates": un_ranked,
            "num_no_ranked_cands": num_no_ranked_cands,
            "is_closed": is_closed,
            "is_completed": document.get("is_completed", False),
            "creation_dt": document.get("creation_dt", None)
            }
    return resp

async def poll_ranking(id, vid): 
    read_concern.ReadConcern('linearizable')
    document = await db.find_one({"_id": ObjectId(id)})  

    # vid could either be a voter id or the owner id
    is_voter, is_owner = voter_type(document, vid, vid)
    
    is_closed = poll_closed( 
                document.get("closing_datetime", None), 
                document.get("timezone", None))
    v_can_vote = can_vote(
                vid,
                document.get("is_private", False),
                document.get("voter_ids",[]),
                document.get("closing_datetime", None), 
                document.get("timezone", None))
    v_can_view_outcome = can_view_outcome(
                document.get("closing_datetime", None), 
                document.get("timezone", None), 
                document.get("can_view_outcome_before_closing", False), 
                document.get("show_outcome", False),
                is_owner,
                is_voter)

    if document is None: # poll not found
        resp = {
            "error": "Poll not found.",
            "poll_found": False,
            "closing_datetime": "n/a",
            "timezone": "n/a",
            "is_closed": False,
            "can_vote": False,
            "can_view_outcome": False
            }
    else: 
        resp = {
            "title": document["title"],
            "description": document["description"],
            "candidates": document["candidates"],
            "is_private": document["is_private"],
            "ranking": {},
            "closing_datetime": document.get("closing_datetime", "n/a"),
            "timezone": document.get("timezone", "n/a"),
            "is_closed": is_closed,
            "can_vote": v_can_vote,
            "can_view_outcome": v_can_view_outcome
            }
        if document["is_private"] and (vid is not None and vid in document["voter_ids"]): 
            for b in document["ballots"]: 
                if b["voter_id"] == vid: 
                    resp["ranking"] = b["ranking"]
    print("RETURNING>>>>>")
    print(resp)
    return resp

async def submit_ballot(ballot, id, vid):
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

async def add_rankings(id, owner_id, csv_file, overwrite): 
    document = await db.find_one({"_id": ObjectId(id)})  
    if document is None: # poll not found
        return {"error": "Poll not found."}
    else: 
        if owner_id != document["owner_id"]:
            return {"error": "Only the poll creater can add rankings to a poll."}
        else: 
            file_location = f"./tmpcsvfiles/{str(uuid.uuid4())}-{csv_file.filename}"
            new_ballots = list()
            with open(file_location, "wb+") as file_object:
                file_object.write(csv_file.file.read())
            with open(file_location) as csvfile:
                ranking_reader = csv.reader(csvfile, delimiter=',')
                _cands = next(ranking_reader)
                cands = [c for c in _cands if (c is not None and c.strip() != '')]
                print(cands)
                if not sorted(document["candidates"]) == sorted(cands):
                    return {"error": "The candidates in the file do not match the candidates in the poll."}
                
                for rowidx, row in enumerate(ranking_reader):
                    new_ballots += [{
                        "ranking": {c:int(r) for c,r in zip(cands, row) if r != ''},
                        "voter_id": f"bulk{rowidx}",
                        "submission_date": None,
                        "ip": csv_file.filename
                    }] 

                curr_ballots = document["ballots"]
                if overwrite: 
                    await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": new_ballots}})
                    success_message = f"Replaced all the ballots with {len(new_ballots)} ballots in the poll: {document['title']}."
                else: 
                    await db.update_one( {"_id": ObjectId(id)}, {"$set": {"ballots": curr_ballots + new_ballots}})
                    success_message = f"Added {len(new_ballots)} ballots to the poll: {document['title']}."
                os.remove(file_location)
                return {"success": success_message}

async def delete_ballot(id, vid):
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

async def delete_poll(id, oid):

    result = await db.delete_one( {"_id": ObjectId(id), "owner_id": oid})
    if result.deleted_count == 0: 
        return {"error": "Poll not deleted."}
    else: 
        return {"success": "Poll deleted."}

async def update_poll(id, owner_id, poll_data: UpdatePoll, background_tasks: BackgroundTasks):
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
            "is_completed": document["is_completed"],
            "result_id": document["result_id"],
            "creation_dt": document["creation_dt"],
            }
        resp = {"success": "Poll updated."}
        if len(document["ballots"]) > 0: 
            new_poll["candidates"] = document["candidates"]
            resp["message"] = "Since voters have submitted ballots, candidates names cannot be changes.   The other changes have been made to the poll." 
        else: 
            new_poll["candidates"] =  get_data("candidates") 
        
        result = await db.update_one({"_id": ObjectId(id)}, {"$set": new_poll})
        if len(new_voter_ids) > 0: 
            for em,voter_id in zip(poll_data["new_voter_emails"], new_voter_ids):
                print("sending email to ", em)
                link = f"https://stablevoting.org/vote/{id}?vid={voter_id}"
                print(participate_email(new_poll["title"], new_poll["description"], link))
                message = MessageSchema(
                    subject=f'Participate in the poll: {new_poll["title"]}',
                    recipients= [em],
                    body = participate_email(poll_data["title"], new_poll["description"], link),
                    subtype=MessageType.html
                    )
                fm = FastMail(conf)

                background_tasks.add_task(fm.send_message,message)

    return resp

async def poll_outcome(id, owner_id, voter_id):
    MAX_NUM_EDGES = 60
    if len(id) != 24: # invalid id
        return {"error": "Poll not found."}
    document = await db.find_one({"_id": ObjectId(id)}) 
    error_message = ''
    if document is None: # poll not found
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
        is_closed = poll_closed(document.get("closing_datetime", None), document.get("timezone", None))
        closing_datetime =  dt_string(document.get("closing_datetime", None), document.get("timezone", None))
        timezone = document["timezone"] if document["timezone"] is not None else "N/A"
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
        splitting_numbers = None
        num_rows = 0
        columns = [[]]

        if can_view and len(document["ballots"]) > 0:
            prof = ProfileWithTies([r["ranking"] for r in document["ballots"]], len(document["candidates"]))
            prof.display()
            if document.get("is_completed", False) and document.get("result_id", None) is not None: 
                response = True
            if not any([len(list(r.rmap.keys())) > 0 for r in prof.rankings]):
                error_message = "No candidates are ranked."
            else: 
                margins = {c1: {c2: prof.margin(c1, c2) for c2 in prof.candidates} for c1 in prof.candidates}
                cw = prof.condorcet_winner()

                try:
                    sc_defeat = func_timeout(5, split_cycle_defeat, args=(prof,), kwargs=None)
                    sc_winners = [str(c) for c in prof.candidates if not any([c2 for c2 in prof.candidates if sc_defeat.has_edge(c2,c)])]
                    defeat_relation = {str(c): {str(c2): sc_defeat.has_edge(c,c2) for c2 in prof.candidates} for c in prof.candidates }
                except FunctionTimedOut:
                    sc_defeat = dict()
                    sc_winners = split_cycle_faster(prof)
                    defeat_relation = {str(c): {} for c in prof.candidates }

                try:
                    sv_winners, _, explanations = func_timeout(5, stable_voting_with_explanations_, args=(prof,), kwargs = {"curr_cands": None, "mem_sv_winners": {}, "explanations": {}})
                except FunctionTimedOut:
                    sv_winners = stable_voting_faster(prof)
                    explanations = dict()
                
                #if len(prof.margin_graph().edges) > MAX_NUM_EDGES: 
                #    sc_defeat = dict()
                #    sc_winners = split_cycle_faster(prof)
                #    defeat_relation = {str(c): {} for c in prof.candidates }
                #    sv_winners = stable_voting_faster(prof)
                #    explanations = dict()
                #else:
                #    sc_defeat = split_cycle_defeat(prof)
                #    sc_winners = [str(c) for c in prof.candidates if not any([c2 for c2 in prof.candidates if sc_defeat.has_edge(c2,c)])]
                #    defeat_relation = {str(c): {str(c2): #sc_defeat.has_edge(c,c2) for c2 in prof.candidates} for c in prof.candidates }
                #    sv_winners, _, explanations = stable_voting_with_explanations_(prof, curr_cands = None, mem_sv_winners = {}, explanations = {})
                
                num_voters = prof.num_voters
                prof_is_linear, linear_order = is_linear(prof)
                columns, num_rows = generate_columns_from_profiles(prof)

                if cw is None: 
                    try:
                        splitting_numbers = func_timeout(5, get_splitting_numbers, args=(prof,), kwargs=None)
                    except FunctionTimedOut:
                        splitting_numbers = {}
                    #splitting_numbers = get_splitting_numbers(prof)
                else: 
                    splitting_numbers = {}
    resp = {
        "title": title,
        "is_closed": is_closed,
        "can_view": can_view,
        "closing_datetime": closing_datetime,
        "timezone": timezone,
        "election_id": str(id),
        "margins": margins, 
        "num_voters": str(num_voters),
        "show_rankings": show_rankings, 
        "sv_winners": sv_winners, 
        "sc_winners": sc_winners, 
        "condorcet_winner": condorcet_winner, 
        "explanations": explanations,
        "defeats": defeat_relation,
        "has_defeats": any([len(defeat_relation[c].values()) != 0  for c in defeat_relation.keys()]),
        "splitting_numbers": splitting_numbers,
        "prof_is_linear": prof_is_linear,
        "linear_order": linear_order if prof_is_linear else [],
        "num_rows": num_rows,
        "columns":columns
        }
    print("resp is ")
    print(resp)
    if error_message != '':
        resp["error"] = error_message
    return resp

async def send_owner_emails(emails_data, id, background_tasks, oid=None): 
    
    for em in emails_data.emails:
        message = MessageSchema(
            subject=f"Created poll: {emails_data.title}",
            recipients= [em],
            body = f"""You have created the poll: {emails_data.title}.<br/><p>Use this link to vote in the poll: {emails_data.vote_link}</p>
            <p>Use this link to view the results of the poll: {emails_data.results_link}</p>
            <p>Use this link to manage the poll: {emails_data.admin_link}</p>
            <p>{"The poll is private." if emails_data.is_private else "The poll is not private."}</p>
            <p>Closing date: {emails_data.closing_datetime}</p>""",
            subtype=MessageType.html
             )
        fm = FastMail(conf)

        background_tasks.add_task(fm.send_message,message)

    return {"success": "Emails sent."}

