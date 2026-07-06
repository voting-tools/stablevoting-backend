## Helpers
#

import secrets


def generate_voter_ids(num_voters):
    '''generate num_voters unique ids'''

    # ids are capability tokens (an oid grants poll administration, a vid grants
    # a voter's ballot), so they must come from a cryptographically secure source
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    ids = [''.join(secrets.choice(alphabet) for _ in range(8)) for _ in range(num_voters)]

    while len(ids) != len(list(set(ids))):
        ids = [''.join(secrets.choice(alphabet) for _ in range(8)) for _ in range(num_voters)]
    return ids

