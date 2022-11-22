from fastapi import APIRouter, HTTPException, BackgroundTasks, File, UploadFile

from bson import ObjectId
from polls.manage import create_poll, update_poll, delete_poll, submit_ballot, delete_ballot, add_rankings, poll_outcome
from polls.models import CreatePoll, UpdatePoll, PollInfo,  Ballot
router = APIRouter()

'''
/poll/create
/poll/1234?include_ranking='blah...'
/poll/outcome/1234
/poll/vote/1234
/poll/delete_ballot/1234/9999
/poll/bulk_vote/1234
/poll/update/1234
/poll/delete/1234
'''
#
# Manage polls
#


@router.post("/polls/create", tags=["polls"])
async def create_a_poll(poll_data: CreatePoll, background_tasks: BackgroundTasks,):
    '''
    create a poll
    '''
    print("Creating a poll with ", poll_data)
    response = await create_poll(background_tasks, poll_data)
    #response = {"id": str(1234), "owner_id": str(4567)}
    print("response is ", response)
    if response:
        return response
    raise HTTPException(400, "Something went wrong")

@router.post("/update/{id}", tags=["polls"])
async def update_a_poll(id, background_tasks: BackgroundTasks, poll_data: UpdatePoll, oid:str = None):
    print("update a poll ", id)
    print("oid ", oid)
    print("poll_data ", poll_data)
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


@router.delete("/delete/{id}",  tags=["polls"])
async def delete_a_poll(id, oid:str = None):
    print("delete poll ", id)
    print("oid ", oid)
    
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


@router.get("/{id}",  tags=["polls"])
async def get_poll(id, oid:str=None, vid:str=None) -> PollInfo:
    print("getting poll data for ", id)
    print("with oid  ", oid)
    print("with vid  ", vid)
    # response = await poll_data(id, oid, vid)

    response = {
        "title": "Test poll",
        "candidates": ["A", "B", "C"],
        "ranking": {},
        "is_private": False, 
        "can_view_outcome": True
    }
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


#
# Ballots and voting
#


@router.post("/vote/{id}",  tags=["polls"])
async def submit_a_ballot(id, ballot: Ballot, vid:str=None, oid:str=None):
    response = await submit_ballot(ballot, id, vid)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@router.delete("/delete_ballot/{id}",  tags=["polls"])
async def delete_a_ballot(id, vid:str=None):
    print("deleting a ballot for poll ", id)
    print("vid ", vid)
    response = await delete_ballot(id, vid)
    
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@router.post("/bulk_vote/{id}", description="Upload rankings as a csv file", tags=["polls"])
async def bulk_add_rankings(id, csv_file: UploadFile = File(...), overwrite: bool=False, oid: str = None):
    print("overwrite")
    print(overwrite)
    print(csv_file)
    response = await add_rankings(id, oid, csv_file, overwrite)
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


@router.get("/outcome/{id}", tags=["polls"])
async def get_poll_outcome(id, oid:str=None, vid:str=None):
    print("get poll outcome for ", id)
    print("oid ", oid)
    print("vid ", vid)
    
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
