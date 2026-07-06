#
# Tests for CSV bulk upload and the email endpoint authorization.
#

from tests.conftest import mongo

CSV_OK = "A,B,C\n1,2,3\n2,1,3,2\n"


def upload(client, poll, content, overwrite=False):
    return client.post(
        f"/polls/bulk_vote/{poll['id']}",
        params={"oid": poll["owner_id"], "overwrite": overwrite},
        files={"csv_file": ("rankings.csv", content.encode(), "text/csv")},
    )


def test_bulk_upload_adds_ballots(client, make_poll):
    poll = make_poll()
    assert upload(client, poll, CSV_OK).status_code == 200
    info = client.get(f"/polls/data/{poll['id']}", params={"oid": poll["owner_id"]}).json()
    assert info["num_ballots"] == 3  # one row + one row counted twice


def test_bulk_upload_overwrite(client, make_poll, vote):
    poll = make_poll()
    vote(poll["id"], {"C": 1})
    assert upload(client, poll, CSV_OK, overwrite=True).status_code == 200
    info = client.get(f"/polls/data/{poll['id']}", params={"oid": poll["owner_id"]}).json()
    assert info["num_ballots"] == 3


def test_bulk_upload_mismatched_candidates(client, make_poll):
    poll = make_poll()
    resp = upload(client, poll, "X,Y,Z\n1,2,3\n")
    assert resp.status_code == 403
    assert "do not match" in resp.json()["detail"]


def test_bulk_upload_non_numeric_rank(client, make_poll):
    poll = make_poll()
    resp = upload(client, poll, "A,B,C\n1,first,3\n")
    assert resp.status_code == 403
    assert "not a number" in resp.json()["detail"]


def test_bulk_upload_requires_owner(client, make_poll):
    poll = make_poll()
    resp = client.post(
        f"/polls/bulk_vote/{poll['id']}",
        params={"oid": "wrong"},
        files={"csv_file": ("r.csv", CSV_OK.encode(), "text/csv")},
    )
    assert resp.status_code == 403


# --- email endpoint authorization (the open-relay regression) ---

VOTER_PAYLOAD = {
    "emails": ["voter@example.com"],
    "link": "https://stablevoting.org/vote/x",
    "title": "Test Poll",
    "description": None,
}

OWNER_PAYLOAD = {
    "emails": ["owner@example.com"],
    "title": "Test Poll",
    "description": None,
    "vote_link": "https://stablevoting.org/vote/x",
    "results_link": "https://stablevoting.org/results/x",
    "admin_link": "https://stablevoting.org/admin/x",
    "is_private": False,
    "closing_datetime": None,
}


def test_regression_send_to_voters_requires_owner(client, make_poll):
    poll = make_poll()
    assert client.post(f"/emails/send_to_voters/{poll['id']}", params={"oid": "wrong"}, json=VOTER_PAYLOAD).status_code == 403
    assert client.post(f"/emails/send_to_voters/{poll['id']}", json=VOTER_PAYLOAD).status_code == 403
    assert client.post("/emails/send_to_voters/000000000000000000000000", params={"oid": "x"}, json=VOTER_PAYLOAD).status_code == 403


def test_send_to_voters_as_owner(client, make_poll):
    poll = make_poll()
    resp = client.post(f"/emails/send_to_voters/{poll['id']}", params={"oid": poll["owner_id"]}, json=VOTER_PAYLOAD)
    assert resp.status_code == 200


def test_regression_send_to_owner_requires_owner(client, make_poll):
    poll = make_poll()
    assert client.post(f"/emails/send_to_owner/{poll['id']}", params={"oid": "wrong"}, json=OWNER_PAYLOAD).status_code == 403


def test_send_to_owner_as_owner(client, make_poll):
    poll = make_poll()
    resp = client.post(f"/emails/send_to_owner/{poll['id']}", params={"oid": poll["owner_id"]}, json=OWNER_PAYLOAD)
    assert resp.status_code == 200


def test_contact_form(client):
    resp = client.post("/emails/send_contact_form", json={"name": "T", "email": "t@example.com", "message": "Hi"})
    assert resp.status_code == 200
