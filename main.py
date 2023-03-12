from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from model import CreatePoll, Ballot, PollInfo, DeleteBallot, UpdatePoll, ContactFormMessage, VoteEmailsData, OwnerEmailsData


app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://localhost",
    "https://stablevoting.org",
    "https://dev.stablevoting.org",
    "http://dev.stablevoting.org"
]

from database import (
    create_poll,
    poll_ranking,
    poll_data,
    submit_ballot,
    delete_ballot,
    delete_poll,
    update_poll,
    add_rankings,
    poll_outcome,
    send_email, 
    send_vote_emails,
    send_owner_emails
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Stable Voting"}

@app.post("/", description="Create a poll", tags=["Polls"])
async def create_a_poll(background_tasks: BackgroundTasks, poll_data: CreatePoll):
    print("create a poll")
    response = await create_poll(background_tasks, poll_data)
    print("response is ", response)
    if response:
        return response
    raise HTTPException(400, "Something went wrong")

@app.post("/bulk/{id}", description="Upload rankings as a csv file", tags=["Polls"])
async def bulk_add_rankings(id, csv_file: UploadFile = File(...), overwrite: bool=False, oid: str = None):
    response = await add_rankings(id, oid, csv_file, overwrite)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.get("/{id}",  tags=["Polls"])
async def get_poll_data(id, oid:str = None) -> PollInfo:
    print("getting poll data")
    print("id is ", id)
    print("oid is ", oid)
    response = await poll_data(id, oid)
    print(response)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.get("/pd/{id}",  tags=["Polls"])
async def get_poll_data2(id, oid:str = None) -> PollInfo:
    print("getting poll data")
    print("id is ", id)
    print("oid is ", oid)
    response = await poll_data(id, oid)
    print(response)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.get("/pr/{id}",  tags=["Polls"])
async def get_poll_ranking(id, vid:str = None) -> PollInfo:
    print("HERE get poll and ranking")
    response = await poll_ranking(id, vid)
    print(f"RESPONSE /pr/{id}", response)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.post("/v/{id}",  tags=["Polls"])
async def submit_a_ballot(id, ballot: Ballot, vid:str = None, oid:str = None):
    response = await submit_ballot(ballot, id, vid)
    print("submitting a ballot")
    print(response)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.get("/d/{id}",  tags=["Polls"])
async def delete_a_poll(id, oid:str = None):
    print("deleting a ballot")
    response = await delete_poll(id, oid)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.post("/db/{id}",  tags=["Polls"])
async def delete_a_ballot(id, vid: DeleteBallot):
    print("deleting a ballot")
    response = await delete_ballot(id, vid.voter_id)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.post("/u/{id}", tags=["Polls"])
async def update_a_poll(id, background_tasks: BackgroundTasks, poll_data: UpdatePoll, oid:str = None):
    print("update a poll")
    response = await update_poll(id, oid, poll_data, background_tasks)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")


@app.get("/o/{id}", tags=["Polls"])
async def get_poll_outcome(id, oid:str = None, vid:str = None):
    print("get poll outcome")
    print("vid is ", vid)
    response = await poll_outcome(id, oid, vid)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@app.post("/sendmessage", tags=["Polls"])
async def send_contact_form_message(contact_form_message: ContactFormMessage, background_tasks: BackgroundTasks, owner_id:str = None, voter_id:str = None):
    print("send message to stablevoting.org@gmail.com")
    response = await send_email(contact_form_message, background_tasks, voter_id, owner_id)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")


@app.post("/send_emails/{id}", tags=["Polls"])
async def send_emails(id, emails_data: VoteEmailsData, background_tasks: BackgroundTasks, oid:str = None):
    print("send emails")
    response = await send_vote_emails(emails_data, id, background_tasks, oid)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")


@app.post("/send_owner_email/{id}", tags=["Polls"])
async def send_owner_email(id, emails_data: OwnerEmailsData, background_tasks: BackgroundTasks, oid:str = None):
    print("send emails")
    response = await send_owner_emails(emails_data, id, background_tasks, oid)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")
