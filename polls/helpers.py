## Helpers
#

import random


def generate_voter_ids(num_voters): 
    '''generate num_voters unique ids'''
    
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    ids =   [''.join(random.choices(alphabet, k=8)) for _ in range(num_voters)]

    while len(ids) != len(list(set(ids))): 
        ids =  [''.join(random.choices(alphabet, k=8)) for _ in range(num_voters)]
    return ids

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

