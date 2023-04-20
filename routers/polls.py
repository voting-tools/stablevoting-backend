from fastapi import APIRouter, HTTPException, BackgroundTasks, File, UploadFile

from bson import ObjectId
from polls.manage import create_poll, update_poll, delete_poll, submit_ballot, delete_ballot, add_rankings, poll_outcome, poll_information, submitted_ranking_information, poll_ranking_information, demo_poll_outcome
from polls.models import CreatePoll, UpdatePoll, PollInfo,  Ballot, PollRankingInfo, RankingsInfo, OutcomeInfo, DemoRankingsInput

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
    print("returning ", response)
    if response:
        return response
    raise HTTPException(400, "Something went wrong")

@router.post("/polls/update/{id}", tags=["polls"])
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


@router.delete("/polls/delete/{id}",  tags=["polls"])
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


@router.get("/polls/submitted_rankings/{id}",  tags=["polls"])
async def get_submitted_ranking_information(id, oid:str=None) -> RankingsInfo:
    print("getting poll data for ", id)
    print("with vid  ", oid)
    
    response = await submitted_ranking_information(id,  oid)

    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@router.get("/polls/data/{id}",  tags=["polls"])
async def get_poll(id, oid:str=None) -> PollInfo:
    print("getting poll data for ", id)
    print("with oid  ", oid)
    
    response = await poll_information(id,  oid)

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

@router.get("/polls/ranking_information/{id}",  tags=["polls"])
async def get_information_for_ranking(id, vid:str=None, allowmultiplevote:str=None) -> PollRankingInfo:
    response = await poll_ranking_information(id, vid, allowmultiplevote)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")




@router.post("/polls/vote/{id}",  tags=["polls"])
async def submit_a_ballot(id, 
                          ballot: Ballot, 
                          vid:str=None, 
                          oid:str=None, 
                          allowmultiplevote:str=None):
    
    print("allowmultiplevote", allowmultiplevote)
    response = await submit_ballot(ballot, id, vid, allowmultiplevote)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response["error"],
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")

@router.delete("/polls/delete_ballot/{id}",  tags=["polls"])
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

@router.post("/polls/bulk_vote/{id}", description="Upload rankings as a csv file", tags=["polls"])
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


@router.post("/polls/outcome/{id}", tags=["polls"])
async def get_poll_outcome(id, rankings_data: DemoRankingsInput, oid:str=None, vid:str=None, ) -> OutcomeInfo:
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

@router.post("/polls/demo_outcome", tags=["polls"])
async def get_demo_poll_outcome(rankings_data: DemoRankingsInput) -> OutcomeInfo:
    print("get poll outcome for ", rankings_data)
    
    response = await demo_poll_outcome(rankings_data.rankings)

    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")
