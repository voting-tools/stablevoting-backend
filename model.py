from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from pydantic import Field, EmailStr
from bson import ObjectId
    
class Ballot(BaseModel): 
    ranking: Dict[str, int]
    voter_id: Optional[str]
    submission_date: Optional[str]
    ip: Optional[str]
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

class ContactFormMessage(BaseModel): 
    name: Optional[str]
    email: Optional[str]
    message: str
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        schema_extra = {
            "example": {
                "name": "Some Person",
                "email": "mail@mail.com",
                "message": "This is a test message"
            }
        }

class DeleteBallot(BaseModel):
    voter_id: str

class VoteEmailsData(BaseModel):
    emails: List[str]
    link: str
    title: str
    description: Optional[str]

class OwnerEmailsData(BaseModel):
    emails: List[str]
    title: str
    description: Optional[str]
    vote_link: str
    results_link: str
    admin_link: str
    is_private: Optional[bool]
    closing_datetime: Optional[str]

class CreatePoll(BaseModel):
    title: str = Field(..., description = "Title of the poll")
    description: Optional[str] 
    candidates: list = Field(..., description = "List of candidates")
    is_private: bool = False
    voter_emails: List[str] = [] # not saved in the database
    show_rankings: bool = True
    closing_datetime: Optional[str]
    timezone: Optional[str]
    can_view_outcome_before_closing: bool = True
    show_outcome: bool = True
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

class PollInfo(BaseModel):
    title: str
    description: Optional[str]
    candidates: list
    is_private: bool
    ranking: Dict[str, int] = {}
    can_view_outcome: bool
    can_vote: Optional[bool]
    closing_datetime: Optional[str]

class UpdatePoll(BaseModel):
    title: Optional[str]
    description: Optional[str] 
    candidates: Optional[List[str]]
    is_private: Optional[bool]
    new_voter_emails: Optional[List[str]] # not saved in the database
    show_rankings: Optional[bool]
    closing_datetime: Optional[str]
    timezone: Optional[str]
    can_view_outcome_before_closing: Optional[bool]
    show_outcome: Optional[bool]
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
