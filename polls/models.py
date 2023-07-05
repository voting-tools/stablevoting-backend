from typing import Optional, List, Dict, Union
from pydantic import BaseModel
from pydantic import Field
from bson import ObjectId

class CreatePoll(BaseModel):
    title: str # title of the poll
    description: Union[str, None] = None # description of the poll
    candidates: List[str] # list of candidates
    is_private: bool = False # if True, only accept votes from specified list of voters
    voter_emails: List[str] = [] # list of emails for the voters, not saved in the database
    show_rankings: bool = True # show the rankings on the outcome page
    closing_datetime: Optional[str] # when the poll closes
    timezone: Optional[str] # timezone of the person creating the poll
    can_view_outcome_before_closing: bool = True # if True, can view the outcome before the poll closes
    show_outcome: bool = True # if True, anyone can view the outcome of the poll with the results link

    class Config:
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
    title: Union[str, None] = None
    description: Union[str, None] = None
    candidates: Union[List[str], None] = None
    is_private: Union[bool, None] = None
    is_completed: Union[bool, None] = None
    new_voter_emails: Union[List[str], None] = None # not saved in the database
    show_rankings: Union[bool, None] = None
    closing_datetime: Union[str, None] = None
    timezone: Union[str, None] = None
    can_view_outcome_before_closing: Union[bool, None] = None
    show_outcome: Union[bool, None] = None
    is_completed: Union[bool, None] = None

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
   
class PollInfo(BaseModel):
    is_owner: bool
    title: str
    creation_dt: str
    description: Union[str, None] = None 
    candidates: List[str]
    num_ballots: int
    is_private: bool
    num_invited_voters: Union[int, None] = None
    is_closed: bool
    is_completed: bool
    show_rankings: bool
    closing_datetime: Union[str, None] = None
    timezone: Union[str, None] = None
    show_outcome: bool
    can_view_outcome_before_closing: bool

class RankingsInfo(BaseModel):
    #candidates: List[str]
    num_voters: int # number of voters
    num_empty_ballots: int # number of voters that submitted empty ballots
    unranked_candidates: List[str] # list of candidates not ranked by any voters
    columns: List[List[Union[int, str]]]
    csv_data: List[List[Union[int, str]]] = [[]]
    num_rows: int

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
    no_candidates_ranked: Union[bool, None]
    one_ranked_candidate: Union[bool, None]
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

