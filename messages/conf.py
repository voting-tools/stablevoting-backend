
from fastapi_mail import ConnectionConfig
import os

SKIP_EMAILS = False # if true, skip sending emails
SV_EMAIL = ['stablevoting.org@gmail.com']
ALL_EMAILS = ['stablevoting.org@gmail.com', 'epacuit@umd.edu','wesholliday@berkeley.edu']

email_username = os.getenv('EMAIL_USERNAME')
print(email_username)
email_pass = os.getenv('EMAIL_PASS')

email_conf = ConnectionConfig(
    MAIL_USERNAME = email_username,
    MAIL_PASSWORD = email_pass,
    MAIL_FROM = "stablevoting.org@gmail.com",
    MAIL_PORT = 587,
    MAIL_SERVER ='smtp.sendgrid.net', # "smtp.gmail.com",
    MAIL_FROM_NAME="Stable Voting",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    #MAIL_TLS=True,
    #MAIL_SSL=False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

