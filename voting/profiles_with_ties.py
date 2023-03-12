from  tabulate import tabulate
from itertools import permutations, combinations
import random
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
import seaborn as sns

class Ranking(object):
    
    def __init__(self, rmap, cmap = None):
        
        self.rmap = rmap
        self.cmap = cmap if cmap is not None else {c:str(c) for c in rmap.keys()}
        
    @property
    def ranks(self): 
        return sorted(set(self.rmap.values()))
    
    @property
    def cands(self):
        return sorted(list(self.rmap.keys()))
    
    def cands_at_rank(self, r):
        return [c for c in self.rmap.keys() if self.rmap[c] == r]
    
    def strict_pref(self, c1, c2):
        return (c1 in self.rmap.keys() and c2 in self.rmap.keys()) and self.rmap[c1] < self.rmap[c2]
    
    def indiff(self, c1, c2):
        return (c1 not in self.rmap.keys() and c2 not in self.rmap.keys()) or (c1 in self.rmap.keys() and c2 in self.rmap.keys() and self.rmap[c1] == self.rmap[c2])
    
    def weak_pref(self, c1, c2):
        return self.strict_pref(c1,c2) or self.indiff(c1,c2)
    
    def is_linear(self):
        return len(list(self.rmap.keys())) == len(list(self.rmap.values()))
    
    def is_truncated(self, cands):
        return all([c in self.rmap.keys() for c in cands])
    
    def remove_cand(self, a): 
        new_cmap = {c: self.rmap[c] for c in self.rmap.keys() if c != a}
        return Ranking(new_cmap, cmap = self.cmap)
    
    def first(self, cs = None):
        # return the first ranked candidates from a list of candidates cs (or all if cs is None)
        _ranks = list(self.rmap.value()) if cs is None else [self.rmap[c] for c in cs]
        _cands = list(self.rmap.keys())  if cs is None else cs
        min_rank = min(_ranks)
        return sorted([c for c in _cands if self.rmap[c] == min_rank])

    def last(self, cs = None):
        # return the last *ranked* candidates from a list of candidates cs (or all ranked candidates if cs is None)
        _ranks = list(self.rmap.value()) if cs is None else [self.rmap[c] for c in cs]
        _cands = list(self.rmap.keys())  if cs is None else cs
        max_rank = max(_ranks)
        return sorted([c for c in _cands if self.rmap[c] == max_rank])

    # set preferences
    def AAdom(self, c1s, c2s):         
        # return True if every candidate in c1s is weakly preferred to every  candidate in c2s
        
        # check if all candidates are ranked
        #assert set(c1s).union(set(c2s)).issubset(self.rmap.keys()), "Error: candidates in the sets {} and {} are not ranked".format(c1s, c2s)
        return all([all([self.weak_pref(c1, c2) for c2 in c2s]) for c1 in c1s])
    
    def strong_dom(self, c1s, c2s):         
        # return True if AAdom(c1s, c2s) and there is a candidate in c1s that is strictly preferred to every  candidate in c2s
        
        # check if all candidates are ranked
        #assert set(c1s).union(set(c2s)).issubset(self.rmap.keys()), "Error: candidates in the sets {} and {} are not ranked".format(c1s, c2s)
        
        return self.AAdom(c1s, c2s) and any([all([self.strict_pref(c1, c2) for c2 in c2s]) for c1 in c1s])

    def weak_dom(self, c1s, c2s):         
        # return True if AAdom(c1s, c2s) and there is a candidate in c1s that is strictly preferred to some  candidate in c2s
        
        # check if all candidates are ranked
        #assert set(c1s).union(set(c2s)).issubset(self.rmap.keys()), "Error: candidates in the sets {} and {} are not ranked".format(c1s, c2s)
        
        return self.AAdom(c1s, c2s) and any([any([self.strict_pref(c1, c2) for c2 in c2s]) for c1 in c1s])

    def __str__(self):
        r_str = ''
        
        for r in self.ranks:
            cands_at_rank = self.cands_at_rank(r)
            if len(cands_at_rank) == 1:
                r_str += str(self.cmap[cands_at_rank[0]])
            else: 
                r_str += '(' + ''.join(map(lambda c: self.cmap[c], cands_at_rank)) + ')'
        return r_str


class ProfileWithTies(object):
    """
    A profile of strict weak orders
    """
    def __init__(self, rankings, num_cands, rcounts=None, cmap=None, candidates=None):
        """
        Create a profile
        """
        
        assert rcounts is None or len(rankings) == len(rcounts), "The number of rankings much be the same as the number of rcounts"
        
        self.num_cands = num_cands
        self.candidates = sorted(candidates) if candidates is not None else sorted(list(set([c for r in rankings for c in r.keys()])))
        
        self.ranks = list(range(1, num_cands + 1))
        # mapping candidates to candidate names
        self.cmap = cmap if cmap is not None else {c:c for c in self.candidates}
        
        self.rankings = [Ranking(r, cmap=self.cmap) for r in rankings]
        
        # for number of each ranking
        self.rcounts = [1]*len(rankings) if rcounts is None else list(rcounts) 
        
                
        # total number of voters
        self.num_voters = np.sum(self.rcounts)

        # memoize the supports
        self._supports = {c1: {c2: sum(n for r, n in zip(self.rankings, self.rcounts) if r.strict_pref(c1, c2)) 
                              for c2 in self.candidates}
                          for c1 in self.candidates}
    @property
    def rankings_counts(self):
        # getter function to get the rankings and rcounts
        return self.rankings, self.rcounts
    
    def support(self, c1, c2):
        # the number of voters that rank c1 strictly above c2 

        return self._supports[c1][c2]
    
    def margin(self, c1, c2):
        # the number of voters that rank c1 strictly over c2 minus the number
        #   that rank c2 strictly over c2.

        return self._supports[c1][c2] - self._supports[c2][c1]

    def ratio(self, c1, c2):
        # the number of voters that rank c1 strictly over c2 minus the number
        #   that rank c2 strictly over c2.
        
        if self.support(c1,c2) > 0 and self.support(c2, c1): 
            return self.support(c1,c2) / self.support(c2, c1)
        elif self.support(c1, c2) > 0 and self.support(c2, c1) == 0:
            return float(self.num_voters + self.support(c1, c2))
        elif self.support(c1, c2) == 0 and self.support(c2, c1) > 0:
            return 1 / (self.num_voters + self.support(c2, c1))
        elif self.support(c1, c2) == 0 and self.support(c2, c1) == 0: 
            return 1
        
    def majority_prefers(self, c1, c2):
        """Returns True if ``c1`` is majority preferred to ``c2``."""

        return self.margin(c1, c2) > 0

    def condorcet_winner(self, curr_cands=None):
        """Returns the Condorcet winner in the profile restricted to ``curr_cands`` if one exists, otherwise return None.

        The **Condorcet winner** is the candidate that is majority preferred to every other candidate.
        """
        curr_cands = curr_cands if curr_cands is not None else self.candidates

        cw = None
        for c in curr_cands:

            if all([self.majority_prefers(c, c1) for c1 in curr_cands if c1 != c]):
                cw = c
                break
        return cw

    def remove_candidates(self, cands_to_ignore):
        # remove all the candidates from cands_to_ignore from the profile
        # returns a new profile and a dictionary mapping new candidate names to the original names
        #   this is needed since we assume that candidates must be named 0...num_cands - 1
        
        updated_rankings = [{c:r for c,r in rank.rmap.items() if c not in cands_to_ignore} for rank in self.rankings]
        new_num_cands = self.num_cands - len(cands_to_ignore)
        new_candidates = [c for c in self.candidates if c not in cands_to_ignore]
        orig_names = {c:c  for c in new_candidates}
        return ProfileWithTies(updated_rankings, new_num_cands, rcounts=self.rcounts, cmap=self.cmap, candidates = new_candidates), orig_names

    def display(self, cmap=None, style="pretty"):
        # display a profile
        # style defaults to "pretty" (the PrettyTable formatting)
        # other stype options is "latex" or "fancy_grid" (or any style option for tabulate)
        
        cmap = cmap if cmap is not None else self.cmap
        print(tabulate([[' '.join([str(cmap[c]) for c in r.cands_at_rank(rank)]) for r in self.rankings] for rank in self.ranks],
                       self.rcounts, tablefmt=style))    
        
    def margin_graph(self, weight='margin'): 
        # generate the margin graph (i.e., the weighted majority graph)
    
        weight_func = self.margin if weight == 'margin' else self.ratio
        weight_unit = 0 if weight == 'margin' else 1
        mg = nx.DiGraph()
        mg.add_nodes_from(self.candidates)
        mg.add_weighted_edges_from([(c1, c2, weight_func(c1,c2))
                                    for c1 in self.candidates 
                                    for c2 in self.candidates if ((c1 != c2) and (weight_func(c1, c2) > weight_unit))])
        return mg
    
    def has_cycle(self):
        try:
            cycle = nx.find_cycle(self.margin_graph())
        except:
            cycle = list()

        return len(cycle) != 0
    
    def display_margin_graph(self, cmap=None, weight = 'margin'):
        # display the margin graph
        
        # create the margin graph.   The reason not to call the above method margin_graph 
        # is that we may want to apply the cmap to the names of the candidates
        
        weight_func = self.margin if weight == 'margin' else self.ratio
        weight_unit = 0 if weight == 'margin' else 1
        cmap = cmap if cmap is not None else self.cmap
        
        mg = nx.DiGraph()
        mg.add_nodes_from([cmap[c] for c in self.candidates])
        mg.add_weighted_edges_from([(cmap[c1], cmap[c2], weight_func(c1,c2))
                                    for c1 in self.candidates 
                                    for c2 in self.candidates if c1 != c2 if weight_func(c1, c2) > weight_unit])

        pos = nx.circular_layout(mg)
        nx.draw(mg, pos, 
                font_size=20,   font_color='white', node_size=700, 
                width=1, lw=1.5, with_labels=True)
        labels = nx.get_edge_attributes(mg,'weight')
        nx.draw_networkx_edge_labels(mg,pos,edge_labels=labels,font_size=14, label_pos=0.3)
        plt.show()


def strict_weak_orders(A):
    if not A:  # i.e., A is empty
        yield []
        return
    for k in range(1, len(A) + 1):
        for B in combinations(A, k):  # i.e., all nonempty subsets B
            for order in strict_weak_orders(set(A) - set(B)):
                yield [B] + order


