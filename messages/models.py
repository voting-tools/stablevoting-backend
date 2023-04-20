from typing import Optional, List
from pydantic import BaseModel


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


class VoterEmailsData(BaseModel):
    emails: List[str]
    link: str
    title: str
    description: Optional[str]

class OwnerEmailData(BaseModel):
    emails: List[str]
    title: str
    description: Optional[str]
    vote_link: str
    results_link: str
    admin_link: str
    is_private: Optional[bool]
    closing_datetime: Optional[str]
