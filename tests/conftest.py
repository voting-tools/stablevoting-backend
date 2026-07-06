#
# Shared fixtures for the backend test suite.
#
# The app is imported AFTER the environment is configured so the module-level
# mongo client and email config pick up the test settings. Tests run against a
# separate database (StableVotingTest) on the local mongod and never send email.
#

import os

os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
os.environ["MONGO_DB_NAME"] = "StableVotingTest"
os.environ["SKIP_EMAILS"] = "True"
os.environ["ENVIRONMENT"] = "test"
os.environ["POSTMARK_SERVER_TOKEN"] = "POSTMARK_API_TEST"
# all TestClient requests share one client address, so tests that cast several
# ballots in a public poll must use the multiple-vote debug password
os.environ["ALLOW_MULTIPLE_VOTE_PWD"] = "test-multi"

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    """Drop the test polls collection before every test."""
    sync_client = MongoClient("mongodb://localhost:27017")
    sync_client["StableVotingTest"].Polls.drop()
    yield
    sync_client.close()


def mongo():
    return MongoClient("mongodb://localhost:27017")["StableVotingTest"].Polls


@pytest.fixture
def make_poll(client):
    """Create a poll and return the response data (id and owner_id)."""

    def _make_poll(**overrides):
        poll = {
            "title": "Test Poll",
            "description": "A test poll",
            "candidates": ["A", "B", "C"],
            "is_private": False,
            "voter_emails": [],
            "show_rankings": True,
            "closing_datetime": None,
            "timezone": "America/New_York",
            "can_view_outcome_before_closing": True,
            "show_outcome": True,
        }
        poll.update(overrides)
        resp = client.post("/polls/create", json=poll)
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _make_poll


@pytest.fixture
def vote(client):
    """Submit a ballot to a poll (uses the multi-vote password for public polls)."""

    def _vote(poll_id, ranking, vid=None, expect_error=False):
        params = {"allowmultiplevote": "test-multi"}
        if vid is not None:
            params["vid"] = vid
        resp = client.post(
            f"/polls/vote/{poll_id}", params=params, json={"ranking": ranking}
        )
        if not expect_error:
            assert resp.status_code == 200, resp.text
        return resp

    return _vote


@pytest.fixture
def get_outcome(client):
    def _get_outcome(poll_id, oid=None, vid=None):
        params = {}
        if oid is not None:
            params["oid"] = oid
        if vid is not None:
            params["vid"] = vid
        return client.post(f"/polls/outcome/{poll_id}", params=params)

    return _get_outcome
