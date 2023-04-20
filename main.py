from fastapi import FastAPI 
from fastapi.middleware.cors import CORSMiddleware

from routers import polls, emails

origins = [
    "http://localhost:3000",
    "http://localhost",
    "https://stablevoting.org",
    "https://dev.stablevoting.org"
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(polls.router)
app.include_router(emails.router)


@app.get('/')
async def root():
    return {"message": "Stable Voting"}

