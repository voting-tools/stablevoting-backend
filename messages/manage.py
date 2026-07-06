
from bson import ObjectId
from messages.conf import send_email, send_batch_emails, SKIP_EMAILS
from messages.helpers import participate_email


async def is_poll_owner(id, oid):
    """Return True if oid is the owner id of the poll with the given id."""
    from polls.manage import db
    if oid is None or not ObjectId.is_valid(id):
        return False
    document = await db.find_one({"_id": ObjectId(id)})
    return document is not None and document.get("owner_id") == oid


async def send_contact_form_email(message, background_tasks, vid=None, oid=None):
    """Send contact form email to administrators"""
    
    subject = "Contact form message"
    html_body = f"""
    <html>
    <body>
        <h3>New Contact Form Submission</h3>
        <p><strong>Name:</strong> {message.name or 'Not provided'}</p>
        <p><strong>Email:</strong> {message.email or 'Not provided'}</p>
        <p><strong>Message:</strong></p>
        <p>{message.message}</p>
        {f'<p><small>Voter ID: {vid}</small></p>' if vid else ''}
        {f'<p><small>Owner ID: {oid}</small></p>' if oid else ''}
    </body>
    </html>
    """
    
    # Send to all admin emails
    admin_emails = ['stablevoting.org@gmail.com', 'epacuit@umd.edu', 'wesholliday@berkeley.edu']
    for admin_email in admin_emails:
        background_tasks.add_task(
            send_email,
            to_email=admin_email,
            subject=subject,
            html_body=html_body,
            tag="contact-form"
        )
    
    return {"success": f"Message sent to administrators."}


async def send_emails_to_voters(emails_data, id, background_tasks, oid=None):
    """Send invitation emails to voters"""

    if not await is_poll_owner(id, oid):
        return {"error": "You do not have permission to send emails for this poll."}

    # Generate email content
    html_body = participate_email(
        emails_data.title,
        emails_data.description,
        emails_data.link
    )
    
    subject = f"Participate in the poll: {emails_data.title}"
    
    # Send emails in batch
    background_tasks.add_task(
        send_batch_emails,
        recipients=emails_data.emails,
        subject=subject,
        html_body=html_body,
        tag=f"voter-invitation-{id}"
    )
    
    return {"success": f"Emails queued for {len(emails_data.emails)} voters."}


async def send_email_to_owner(emails_data, id, background_tasks, oid=None):
    """Send poll creation confirmation to owner"""

    if not await is_poll_owner(id, oid):
        return {"error": "You do not have permission to send emails for this poll."}

    html_body = f"""
    <html>
    <body>
        <p>Hello from Stable Voting,</p>
        
        <p>You have successfully created the poll: <strong>{emails_data.title}</strong></p>
        
        <h3>Your Poll Links:</h3>
        <ul>
            <li><strong>Vote:</strong> <a href="{emails_data.vote_link}">{emails_data.vote_link}</a></li>
            <li><strong>Results:</strong> <a href="{emails_data.results_link}">{emails_data.results_link}</a></li>
            <li><strong>Admin:</strong> <a href="{emails_data.admin_link}">{emails_data.admin_link}</a></li>
        </ul>
        
        <h3>Poll Settings:</h3>
        <ul>
            <li><strong>Privacy:</strong> {"Private poll" if emails_data.is_private else "Public poll"}</li>
            <li><strong>Closing date:</strong> {emails_data.closing_datetime or "No closing date set"}</li>
        </ul>
        
        <p>Thank you for using Stable Voting!</p>
        
        <br/>
        <p><a href="https://stablevoting.org/about">Learn more about Stable Voting</a></p>
    </body>
    </html>
    """
    
    subject = f"Created poll: {emails_data.title}"
    
    # Send to all specified emails (usually just the owner)
    for email in emails_data.emails:
        background_tasks.add_task(
            send_email,
            to_email=email,
            subject=subject,
            html_body=html_body,
            tag=f"poll-created-{id}"
        )
    
    return {"success": "Owner notification sent."}