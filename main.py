from fastapi import FastAPI 
from routers import polls

app = FastAPI()

app.include_router(polls.router)

@app.get("/")
async def root():
    return {"message": "Stable Voting"}

'''
/email/contact_form
/email/to_owner
/email/to_voters
'''