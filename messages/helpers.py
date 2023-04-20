
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

