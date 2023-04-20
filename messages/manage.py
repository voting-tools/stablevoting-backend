
from fastapi_mail import FastMail, MessageSchema, MessageType
from .conf import email_conf, ALL_EMAILS, SKIP_EMAILS
from messages.helpers import participate_email

async def send_contact_form_email(message, background_tasks, vid=None, oid=None):

    message = MessageSchema(
        subject=f"Contact form message",
        recipients= ALL_EMAILS,
        body = f"""<p>Name: {message.name}</p><p>Email: {message.email} </p><p>Message: {message.message}</p>""",
        subtype=MessageType.html
        )
    if SKIP_EMAILS:
        print(f"Skipped sending email to {ALL_EMAILS}: ", message)
    else:
        fm = FastMail(email_conf)
        background_tasks.add_task(fm.send_message,message)

    return {"success": "Message sent to stablevoting.org@gmail.com."}

async def send_emails_to_voters(emails_data, id, background_tasks, oid=None): 

    for em in emails_data.emails:
        message = MessageSchema(
            subject=f"Participate in the poll: {emails_data.title}",
            recipients= [em],
            body = participate_email(emails_data.title, emails_data.description, emails_data.link),
            subtype=MessageType.html
            )
        if SKIP_EMAILS:
            print(f"Skipped sending email to {em}: ", message)
        else:
            fm = FastMail(email_conf)
            background_tasks.add_task(fm.send_message, message)

    return {"success": "Emails sent."}

async def send_email_to_owner(emails_data, id, background_tasks, oid=None): 
    print(emails_data)
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
        if SKIP_EMAILS:
            print(f"Skipped sending email to {em}: ", message)
        else:
            fm = FastMail(email_conf)
            background_tasks.add_task(fm.send_message, message)


    return {"success": "Emails sent."}

