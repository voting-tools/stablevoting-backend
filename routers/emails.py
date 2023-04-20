from fastapi import APIRouter, HTTPException, BackgroundTasks
from messages.models import ContactFormMessage, VoterEmailsData, OwnerEmailData
from messages.manage import send_contact_form_email, send_emails_to_voters, send_email_to_owner

router = APIRouter()

'''
/emails/sendmessage
/emails/contact_form
/emails/to_owner
/emails/to_voters
'''

@router.post("/emails/send_contact_form", tags=["emails"])
async def sendmessage(contact_form_message: ContactFormMessage, background_tasks: BackgroundTasks, owner_id:str = None, voter_id:str = None):
    
    print("send contact form message to stablevoting.org@gmail.com")
    
    response = await send_contact_form_email(contact_form_message, background_tasks, voter_id, owner_id)

    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")


@router.post("/emails/send_to_voters/{id}", tags=["emails"])
async def send_voter_emails(id, emails_data: VoterEmailsData, background_tasks: BackgroundTasks, oid:str = None):
    print(emails_data)
    print("send emails to voters")
    response = await send_emails_to_voters(emails_data, id, background_tasks, oid)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")


@router.post("/emails/send_to_owner/{id}", tags=["emails"])
async def send_owner_email(id, emails_data: OwnerEmailData, background_tasks: BackgroundTasks, oid:str = None):
    print(emails_data)
    print("send email to owner")
    response = await send_email_to_owner(emails_data, id, background_tasks, oid)
    if response is not None and "error" not in response.keys():
        return response
    elif response is not None:
        raise HTTPException(
            status_code = 403,
            detail = response,
            headers={"X-Error": "Not found"},
        )
    raise HTTPException(400, "Something went wrong")
