from itertools import permutations
import networkx as nx
import numpy as np
def is_linear(profile): 
    
    num_incoming_edges = {c: len([_c for _c in profile.candidates if _c != c and profile.margin(_c,c) > 0]) 
                          for c in profile.candidates}
    
    lin_profile = sorted(list(set(num_incoming_edges.values()))) == list(range(len(profile.candidates)))
    
    return lin_profile, [c for c,_ in sorted(num_incoming_edges.items(), key=lambda ces: ces[1] )]

def split_cycle_faster(profile, curr_cands = None):   
    """Implementation of Split Cycle using a variation of the Floyd Warshall-Algorithm  
    """
    curr_cands = curr_cands if curr_cands is not None else profile.candidates
    mg = [[-np.inf for _ in curr_cands] for _ in curr_cands]
    
    for c1_idx,c1 in enumerate(curr_cands):
        for c2_idx,c2 in enumerate(curr_cands):
            if (profile.support(c1,c2) > profile.support(c2,c1) or c1 == c2):
                mg[c1_idx][c2_idx] = profile.support(c1,c2) - profile.support(c2,c1)    
    strength = list(map(lambda i : list(map(lambda j : j , i)) , mg))
    for i_idx, i in enumerate(curr_cands):         
        for j_idx, j in enumerate(curr_cands): 
            if i!= j:
                for k_idx, k in enumerate(curr_cands): 
                    if i!= k and j != k:
                        strength[j_idx][k_idx] = max(strength[j_idx][k_idx], min(strength[j_idx][i_idx],strength[i_idx][k_idx]))
    winners = {i:True for i in curr_cands}
    for i_idx, i in enumerate(curr_cands): 
        for j_idx,j in enumerate(curr_cands):
            if i!=j:
                if mg[j_idx][i_idx] > strength[i_idx][j_idx]: # the main difference with Beat Path
                    winners[i] = False
    return sorted([c for c in curr_cands if winners[c]])

def generate_rank_count(rc_str):
    
    rcount, rank_str = rc_str.split(":")
    
    r_str = rank_str.strip()
    
    if r_str.find("{") == -1:
        
        c_list = r_str.split(",")
        cvote = {}
        crank = 1
        for _c in c_list: 
            if _c.strip() not in cvote.keys():
                cvote[_c.strip()] = crank
                crank += 1
    else: 
        c_list = r_str.split(",")
        cvote = {}
        crank = 1
        partial = False
        for ccand in c_list:
            if ccand.find("{") != -1:
                partial = True
                t = ccand.replace("{","")
                cvote[t.strip()] = crank
            elif ccand.find("}") != -1:
                partial = False
                t = ccand.replace("}","")
                cvote[t.strip()] = crank
                crank += 1
            else:
                cvote[ccand.strip()] = crank
                if partial == False:
                    crank += 1
                #print("cvote is", cvote)
    return cvote, int(rcount.strip())

def is_same_ranking(r1, r2): 
    if sorted(list(r1.keys())) == sorted(list(r2.keys())):
        return all([r1[c] == r2[c] for c in r1.keys()])
    return False

def ws_to_str(ws): 
    if len(ws) == 1: 
        return f"Stable Voting winner is {ws[0]}"
    elif len(ws) == 2: 
        return f"Stable Voting winners are {ws[0]} and {ws[1]}"
    elif len(ws) > 2: 
        _ws = ws[0:-1]
        return f"Stable Voting winners are {', '.join(map(str, _ws))} and {str(ws[-1])}"
    
def cs_to_str(cs): 
    if len(cs) == 1: 
        return f"{cs[0]}"
    elif len(cs) == 2: 
        return f"{cs[0]} and {cs[1]}"
    elif len(cs) > 2: 
        _cs = cs[0:-1]
        return f"{', '.join(map(str, _cs))} and {str(cs[-1])}"
    
def tuple_to_str(l): 
    return f"{','.join(map(str,l))}"

def at_least_one_ranking(ballots): 
    return any([bool(b["ranking"]) for b in ballots])
    
def find_strengths(profile, curr_cands = None):   
    """
    A path from candidate a to candidate b is a list of candidates starting with a and ending with b 
    such that each candidate in the list has a nonzero margin vs. the next candidate in the list. 
    The strength of a path is the minimum margin between consecutive candidates in the path 
    The strength of the pair of candidates (a,b) is strength of the strongest path from a to b.   
    We find these strengths using the Floyd-Warshall Algorithm.  
    """
    curr_cands = curr_cands if curr_cands is not None else profile.candidates
    mg = [[0 for _ in curr_cands] for _ in curr_cands]
    
    for c1_idx,c1 in enumerate(curr_cands):
        for c2_idx,c2 in enumerate(curr_cands):
            if (profile.support(c1,c2) > profile.support(c2,c1) or c1 == c2):
                mg[c1_idx][c2_idx] = profile.support(c1,c2) - profile.support(c2,c1)    
    strength = list(map(lambda i : list(map(lambda j : j , i)) , mg))
    for i_idx, i in enumerate(curr_cands):         
        for j_idx, j in enumerate(curr_cands): 
            if i!= j:
                for k_idx, k in enumerate(curr_cands): 
                    if i!= k and j != k:
                        strength[j_idx][k_idx] = max(strength[j_idx][k_idx], min(strength[j_idx][i_idx],strength[i_idx][k_idx]))
    return strength

def get_splitting_numbers(profile): 
    '''
    return a dictionary associating each cycle with its splitting number
    '''
    mg = profile.margin_graph()
    cycles = list(nx.simple_cycles(mg)) 
    splitting_numbers = dict()
    for cycle in cycles: # for each cycle in the margin graph
        # get all the margins (i.e., the weights) of the edges in the cycle
        margins = list() 
        for idx,c1 in enumerate(cycle): 
            next_idx = idx + 1 if (idx + 1) < len(cycle) else 0
            c2 = cycle[next_idx]
            margins.append(mg[c1][c2]['weight']) 
        splitting_numbers[tuple_to_str(cycle)] = min(margins) # the split number of the cycle is the minimal margin
    return splitting_numbers

def split_cycle_defeat(profile):
    """A majority cycle in a profile P is a sequence x_1,...,x_n of distinct candidates in 
    P with x_1=x_n such that for 1 <= k <= n-1,  x_k is majority preferred to x_{k+1}.
    The *strength of* a majority is the minimal margin in the cycle.  
    Say that a defeats b in P if the margin of a over b is positive and greater than 
    the strength of the strongest majority cycle containing a and b. The Split Cycle winners
    are the undefeated candidates.
    """
    
    candidates = profile.candidates 
    
    # create the margin graph
    mg = profile.margin_graph()
    
    # find the cycle number for each candidate
    cycle_number = {cs:0 for cs in permutations(candidates,2)}
    for cycle in nx.simple_cycles(mg): # for each cycle in the margin graph

        # get all the margins (i.e., the weights) of the edges in the cycle
        margins = list() 
        for idx,c1 in enumerate(cycle): 
            next_idx = idx + 1 if (idx + 1) < len(cycle) else 0
            c2 = cycle[next_idx]
            margins.append(mg[c1][c2]['weight'])
            
        split_number = min(margins) # the split number of the cycle is the minimal margin
        for c1,c2 in cycle_number.keys():
            c1_index = cycle.index(c1) if c1 in cycle else -1
            c2_index = cycle.index(c2) if c2 in cycle else -1

            # only need to check cycles with an edge from c1 to c2
            if (c1_index != -1 and c2_index != -1) and ((c2_index == c1_index + 1) or (c1_index == len(cycle)-1 and c2_index == 0)):
                cycle_number[(c1,c2)] = split_number if split_number > cycle_number[(c1,c2)] else cycle_number[(c1,c2)]        

    # construct the defeat relation, where a defeats b if margin(a,b) > cycle_number(a,b) (see Lemma 3.13)
    defeat = nx.DiGraph()
    defeat.add_nodes_from(candidates)
    defeat.add_weighted_edges_from([(c1,c2, profile.margin(c1, c2))  
           for c1 in candidates 
           for c2 in candidates if c1 != c2 if profile.margin(c1,c2) > cycle_number[(c1,c2)]])

    return defeat


def stable_voting_with_explanations_(profile, curr_cands = None, mem_sv_winners = {}, explanations = {}): 
    '''
    Determine the Stable Voting winners for the profile while keeping track 
    of the winners in any subprofiles checked during computation. 
    '''
    
    # curr_cands is the set of candidates who have not been removed
    curr_cands = curr_cands if not curr_cands is None else profile.candidates
    sv_winners = list()
    
    if len(curr_cands) == 1: 
        mem_sv_winners[tuple(curr_cands)] = curr_cands
        explanations[tuple_to_str(tuple(curr_cands))] = {} 
        return curr_cands, mem_sv_winners, explanations

    sc_ws = split_cycle_faster(profile, curr_cands = curr_cands)
    print("sc_ws", sc_ws)
    if len(sc_ws) == 1: 
        mem_sv_winners[tuple(curr_cands)] = sc_ws
        explanations[tuple_to_str(tuple(curr_cands))] = {"is_uniquely_undefeated": {
            'winner': tuple_to_str(sc_ws),
            'is_condorcet_winner': all([profile.margin(sc_ws[0], _c) > 0 for _c in curr_cands if sc_ws[0] != _c])}}
        return sc_ws, mem_sv_winners, explanations
    
    matches = [(a, b) for a in curr_cands for b in curr_cands if a != b]    
    margins = list(set([profile.margin(a, b) for a,b in matches]))
    
    for m in sorted(margins, reverse=True):
        for a, b in [ab_match for ab_match in matches 
                     if profile.margin(ab_match[0], ab_match[1])  == m and ab_match[0] in sc_ws]:
            
            if a not in sv_winners: 
                cands_minus_b = sorted([c for c in curr_cands if c!= b])
                if tuple(cands_minus_b) not in mem_sv_winners.keys(): 
                    ws, mem_sv_winners, explanations = stable_voting_with_explanations_(profile, curr_cands = cands_minus_b, mem_sv_winners = mem_sv_winners, explanations = explanations)
                    mem_sv_winners[tuple(cands_minus_b)] = ws
                else: 
                    ws = mem_sv_winners[tuple(cands_minus_b)]
                
                if a in ws:
                    sv_winners.append(a)
                if tuple_to_str(tuple(curr_cands)) not in explanations.keys():
                    explanations[tuple_to_str(tuple(curr_cands))] = dict()
                explanations[tuple_to_str(tuple(curr_cands))].update({tuple_to_str((a,b)): {
                    'margin': str(profile.margin(a,b)), 
                    'cands_minus_b': tuple_to_str([c for c in curr_cands if c != b]),
                    'undefeated_cands': tuple_to_str(sc_ws),
                    'winner': tuple_to_str(ws)}})

        if len(sv_winners) > 0: 
            return sorted(sv_winners), mem_sv_winners, explanations

def generate_columns_from_profiles(prof): 
    cols = list()
    max_rank = 0
    for r in prof.rankings: 
        if len(r.rmap.values()) > 0 and max_rank < max(r.rmap.values()):
            max_rank = max(r.rmap.values())
            
    for r,c in zip(prof.rankings, prof.rcounts):
        found_col=False
        for col in cols: 
            col_rmap = col["rmap"]
            if is_same_ranking(r.rmap, col_rmap): 
                col["count"] += c
                found_col = True
        if not found_col: 
            cols.append({
                "rmap": r.rmap,
                "count": c,
                "col_list": [", ".join([str(_c) for _c in r.cands_at_rank(rank)]) if rank in r.rmap.values() else "" 
                            for rank in range(1, max_rank + 1)]
            })
    return [[str(c["count"])] + c["col_list"] for c in cols], max_rank
