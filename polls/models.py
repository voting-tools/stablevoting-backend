from typing import Optional, List, Dict, Union
from pydantic import BaseModel
from pydantic import Field
from bson import ObjectId

class CreatePoll(BaseModel):
    title: str # title of the poll
    description: Union[str, None] = None # description of the poll
    hide_description: bool = True # if True, initially hide the description on the on the vote page 
    candidates: List[str] # list of candidates
    is_private: bool = False # if True, only accept votes from specified list of voters
    voter_emails: List[str] = [] # list of emails for the voters, not saved in the database
    show_rankings: bool = True # show the rankings on the outcome page
    closing_datetime: Optional[str] = None # when the poll closes
    timezone: Optional[str] = None # timezone of the person creating the poll
    can_view_outcome_before_closing: bool = True # if True, can view the outcome before the poll closes
    show_outcome: bool = True # if True, anyone can view the outcome of the poll with the results link
    allow_multiple_votes: bool = False # allow multiple votes from the same ip address
    put_unranked_candidates_at_bottom: bool = True # if True, candidates not ranked by any voter will be put at the bottom of the rankings
    allow_ties: bool = True # if True, allow ties in the rankings
    num_candidates_to_rank: Optional[int] = None # number of candidates to rank, if None, all candidates must be ranked

    class Config:
        extra = "forbid"
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "title": "Example Election",
                "description": "Example of an election...",
                "candidates": ["A", "B", "C"],
                "is_private": True,
                "voter_emails": ['test@mail.com'],
                "show_rankings": True,
                "closing_datetime": None,
                "timezone": None,
                "can_view_outcome_before_closing": True,
                "show_outcome": True,
            }
        }

class UpdatePoll(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    hide_description: Optional[bool] = None  # Changed default from True to None
    candidates: Optional[List[str]] = None
    is_private: Optional[bool] = None
    is_completed: Optional[bool] = None  # Removed duplicate
    new_voter_emails: Optional[List[str]] = None
    show_rankings: Optional[bool] = None
    closing_datetime: Optional[str] = None
    timezone: Optional[str] = None
    can_view_outcome_before_closing: Optional[bool] = None
    show_outcome: Optional[bool] = None
    allow_multiple_votes: Optional[bool] = None  # Changed default from False to None
    put_unranked_candidates_at_bottom: Optional[bool] = None  # Add if needed
    allow_ties: Optional[bool] = None  # Add if needed
    num_candidates_to_rank: Optional[int] = None  # Add if needed

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        schema_extra = {
            "example": {
                "title": "Update Example Election",
                "description": "Update Example of an election...",
                "candidates": ["A", "B", "C"],
                "is_private": True,
                "new_voter_emails": ['another@mail.com'],
                "show_rankings": True,
                "closing_datetime": None,
                "timezone": None,
                "can_view_outcome_before_closing": True,
                "show_outcome": True,
            }
        }

class PollRankingInfo(BaseModel): 
    title: str
    description: Union[str, None] = None
    hide_description: bool = True # if True, initially hide the description on the vote page
    allow_multiple_vote: bool # allow multiple votes for debugging
    candidates: List[str]
    ranking: Dict[str, int] = {}
    can_vote: bool
    can_view_outcome: bool
    is_completed: bool
    is_closed: bool # true when there is a closing datetime and the current time is past the closing datetime
    is_private: bool
    closing_datetime_str: Union[str, None] = None
    timezone: Union[str, None] = None
    time_remaining_str: Union[str, None] = None # how much time is remaining before the poll closes

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        schema_extra = {
            "example": {
                "title": "Example poll",
                "allow_multiple_vote_pwd": "secret",
                "can_vote": True,
                "can_view_outcome": True,
                "is_closed": False,
                "is_completed": False,
                "is_private": False
            }
        }
   
class VoterDetail(BaseModel):
    voter_id: str
    email: str
    emailsSent: int
    # Removed hasVoted and voteUrl fields for privacy

class PollInfo(BaseModel):
    is_owner: bool
    title: str
    creation_dt: str
    description: Union[str, None] = None 
    hide_description: bool # if True, initially hide the description on the vote page
    election_id: str
    candidates: List[str]
    num_ballots: int
    is_private: bool
    num_invited_voters: Union[int, None] = None
    is_closed: bool
    is_completed: bool
    show_rankings: bool
    allow_multiple_votes: bool
    closing_datetime: Union[str, None] = None
    timezone: Union[str, None] = None
    show_outcome: bool
    can_view_outcome_before_closing: bool
    voter_details: Optional[List[VoterDetail]] = None


class RankingsInfo(BaseModel):
    #candidates: List[str]
    num_voters: int # number of voters
    num_empty_ballots: int # number of voters that submitted empty ballots
    unranked_candidates: List[str] # list of candidates not ranked by any voters
    columns: List[List[str]]
    csv_data: List[List[Union[int, str]]] = [[]]
    num_rows: int
    cmap: Dict[Union[int, str], str] 

class Ballot(BaseModel): 
    ranking: Dict[str, int]
    voter_id: Union[str, None] = None
    submission_date: Union[str, None] = None
    ip: Union[str, None] = None
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        schema_extra = {
            "example": {
                "voter_id": "1234",
                "submission_date": "1/1/2000 12:00:00",
                "ip": "n/a",
                "ranking": {
                    "A": 1, 
                    "B": 2, 
                    "C": 3
                    },
            }
        }

class OutcomeInfo(BaseModel):
    title: str
    election_id: str
    can_view: bool
    is_closed: bool
    is_completed: bool
    cmap: Dict[int, str]
    closing_datetime: Union[str, None]
    no_candidates_ranked: Union[bool, None] = None  # Add = None
    one_ranked_candidate: Union[bool, None] = None  # Add = None
    timezone: Union[str, None]
    margins: Dict 
    num_voters: str
    show_rankings: bool 
    sv_winners: List[str]
    selected_sv_winner: Union[str, None]
    sc_winners: List[str] 
    condorcet_winner: Union[str, None]
    explanations: Dict
    defeats: Dict
    splitting_numbers: Dict
    prof_is_linear: bool
    linear_order: List[str]
    num_rows: int
    columns: List[List[str]]


class DemoRankingsInput(BaseModel):
    rankings: Union[List[Dict], None]

