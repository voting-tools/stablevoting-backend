
from pref_voting.voting_methods import split_cycle
 
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


def is_linear(profile): 
    
    num_incoming_edges = {c: len([_c for _c in profile.candidates if _c != c and profile.margin(_c,c) > 0]) 
                          for c in profile.candidates}
    
    lin_profile = sorted(list(set(num_incoming_edges.values()))) == list(range(len(profile.candidates)))
    
    return lin_profile, [c for c,_ in sorted(num_incoming_edges.items(), key=lambda ces: ces[1] )]

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

def generate_csv_data(profile, cmap): 
    candidates = profile.candidates
    
    # generate the anonymous profile
    rs, cs = profile.rankings_counts
    anon_rankings = [[rs[0], cs[0]]]
    for r, c in zip(rs[1::], cs[1::]): 
        r.normalize_ranks()
        found_it = False
        for r_c in anon_rankings[1::]: 
            if r_c[0] == r: 
                found_it = True
                r_c[1] += c
        if not found_it: 
            anon_rankings.append([r, c])
    
    # generate the rows for the csv file
    rows = [[cmap[c] for c in candidates] + [""]] 
    for r,c in anon_rankings: 
        row = list()
        for cand in candidates: 
            if cand in r.rmap.keys(): 
                row.append(r.rmap[cand])
            else: 
                row.append("")
        row.append(c)
        rows.append(row)

    return rows

def get_splitting_numbers(profile): 
    '''
    return a dictionary associating each cycle with its splitting number
    '''
    cycles = profile.cycles()
    splitting_numbers = dict()
    for cycle in cycles: # for each cycle in the margin graph
        # get all the margins (i.e., the weights) of the edges in the cycle
        margins = list() 
        for idx,c1 in enumerate(cycle): 
            next_idx = idx + 1 if (idx + 1) < len(cycle) else 0
            c2 = cycle[next_idx]
            margins.append(profile.margin(c1, c2)) 
        splitting_numbers[tuple_to_str(cycle)] = min(margins) # the split number of the cycle is the minimal margin
    return splitting_numbers


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

    sc_ws = split_cycle(profile, curr_cands = curr_cands)
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

