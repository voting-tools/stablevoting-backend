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

