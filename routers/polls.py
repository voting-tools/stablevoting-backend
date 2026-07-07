from fastapi import APIRouter, HTTPException, BackgroundTasks, File, Request, UploadFile
from fastapi.responses import StreamingResponse  # ADD THIS
from typing import Optional
from io import BytesIO  # ADD THIS

from bson import ObjectId
from polls.manage import create_poll, update_poll, delete_poll, submit_ballot, delete_ballot, add_rankings, poll_outcome, poll_information, submitted_ranking_information, poll_ranking_information, demo_poll_outcome, delete_voter, regenerate_voter_link, delete_all_ballots, delete_ballot, resend_voter_email, superuser_pwd_valid, superuser_list_polls, superuser_stats
from polls.models import CreatePoll, UpdatePoll, PollInfo,  Ballot, PollRankingInfo, RankingsInfo, OutcomeInfo, DemoRankingsInput
from polls.qr_utils import generate_poll_qr_code  # ADD THIS (note the dot for relative import)

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
    print("POLL DATA")
    print(poll_data)
    response = await create_poll(background_tasks, poll_data)
    print("returning ", response)
    if response:
        return response
    raise HTTPException(400, "Something went wrong")

@router.post("/polls/update/{id}", tags=["polls"])
async def update_a_poll(id, background_tasks: BackgroundTasks, poll_data: UpdatePoll, oid:Optional[str] = None):
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
async def delete_a_poll(id, oid:Optional[str]=None):
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
async def get_submitted_ranking_information(id, oid:Optional[str]=None) -> RankingsInfo:
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
async def get_poll(id, oid:Optional[str]=None) -> PollInfo:
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
async def get_information_for_ranking(id, vid:Optional[str]=None, allowmultiplevote:Optional[str]=None) -> PollRankingInfo:
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
                          request: Request,
                          vid:Optional[str]=None,
                          oid:Optional[str]=None,
                          allowmultiplevote:Optional[str]=None):

    # the voter's address is derived from the request, never trusted from the client
    forwarded = request.headers.get("x-forwarded-for", "")
    ballot.ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "n/a")
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
async def delete_a_ballot(id, vid:Optional[str]=None):
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
async def bulk_add_rankings(id, csv_file: UploadFile = File(...), overwrite: bool=False, oid: Optional[str] = None):
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
async def get_poll_outcome(
    id: str,  # Added type hint
    oid: Optional[str] = None,  # Fixed: Optional[str] instead of str=None
    vid: Optional[str] = None,  # Fixed: Optional[str] instead of str=None
) -> OutcomeInfo:
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

@router.get("/polls/qrcode", tags=["polls"])
async def generate_qr_code(url: str):
    """Generate a QR code for a given URL"""
    try:
        # Generate QR code using your utility
        qr_data = generate_poll_qr_code(url)
        
        # Create a BytesIO object from the image bytes
        img_bytes = BytesIO(qr_data["image_bytes"])
        
        # Return as streaming response
        return StreamingResponse(
            img_bytes, 
            media_type="image/png",
            headers={
                "Content-Disposition": f"inline; filename=qr_code.png"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating QR code: {str(e)}"
        )


@router.get("/polls/superuser/polls", tags=["polls"])
async def get_superuser_polls(pwd: str):
    """Password-gated summary of every poll, for the hidden super-user list.

    Requires the SUPERUSER_PWD environment variable to be set and matched;
    returns 403 otherwise. The response includes owner ids, so it must stay
    behind the password.
    """
    if not superuser_pwd_valid(pwd):
        raise HTTPException(status_code=403, detail="Invalid or missing super-user password.")
    return await superuser_list_polls()


@router.get("/polls/superuser/stats", tags=["polls"])
async def get_superuser_stats(pwd: str):
    """Password-gated analytics over all polls, for the super-user dashboard."""
    if not superuser_pwd_valid(pwd):
        raise HTTPException(status_code=403, detail="Invalid or missing super-user password.")
    return await superuser_stats()


@router.delete("/polls/voters/{poll_id}/{voter_id}", tags=["polls"])
async def delete_a_voter(
    poll_id: str, 
    voter_id: str, 
    oid: Optional[str] = None
):
    """Delete a voter from a private poll"""
    print(f"Deleting voter {voter_id} from poll {poll_id}")
    print(f"Owner ID: {oid}")
    
    response = await delete_voter(poll_id, voter_id, oid)
    
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not authorized"},
        )
    raise HTTPException(400, "Something went wrong")


@router.delete("/polls/ballots/{id}/all", tags=["polls"])
async def delete_all_ballots_endpoint(
    id: str,
    oid: Optional[str] = None
):
    """Delete all ballots from a poll"""
    print(f"Deleting all ballots from poll {id}")
    print(f"Owner ID: {oid}")
    
    response = await delete_all_ballots(id, oid)
    
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not authorized"},
        )
    raise HTTPException(400, "Something went wrong")

@router.post("/polls/voters/{poll_id}/{voter_id}/regenerate", tags=["polls"])
async def regenerate_voter_link_endpoint(
    poll_id: str,
    voter_id: str,
    background_tasks: BackgroundTasks,
    oid: Optional[str] = None
):
    """Generate a new voter ID/link for an existing voter"""
    print(f"Regenerating link for voter {voter_id} in poll {poll_id}")
    print(f"Owner ID: {oid}")
    
    response = await regenerate_voter_link(poll_id, voter_id, oid, background_tasks)
    
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not authorized"},
        )
    raise HTTPException(400, "Something went wrong")


@router.post("/polls/voters/{poll_id}/resend", tags=["polls"])
async def resend_voter_email_endpoint(
    poll_id: str,
    background_tasks: BackgroundTasks,
    request_body: dict,
    oid: Optional[str] = None
):
    """Resend invitation email to a voter"""
    email = request_body.get("email")
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required"
        )
    
    print(f"Resending email to {email} for poll {poll_id}")
    print(f"Owner ID: {oid}")
    
    response = await resend_voter_email(poll_id, email, oid, background_tasks)
    
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code=403,
            detail=response["error"],
            headers={"X-Error": "Not authorized"},
        )
    raise HTTPException(400, "Something went wrong")