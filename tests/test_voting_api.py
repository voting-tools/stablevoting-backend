#
# API tests for ballot submission and outcome computation, including regression
# tests for the ported bug fixes.
#

from tests.conftest import mongo

PAST = "2020-01-01T00:00:00+00:00"


def close_poll(client, poll, closing_datetime=PAST):
    resp = client.post(
        f"/polls/update/{poll['id']}",
        params={"oid": poll["owner_id"]},
        json={"closing_datetime": closing_datetime, "timezone": "UTC"},
    )
    assert resp.status_code == 200


def cand_name(outcome, idx):
    return outcome["cmap"][str(idx)]


def winners(outcome):
    return sorted(cand_name(outcome, w) for w in outcome["sv_winners"])


def test_vote_and_simple_majority_winner(make_poll, vote, get_outcome):
    poll = make_poll()
    vote(poll["id"], {"A": 1, "B": 2, "C": 3})
    vote(poll["id"], {"A": 1, "C": 2, "B": 3})
    vote(poll["id"], {"B": 1, "A": 2, "C": 3})
    outcome = get_outcome(poll["id"], oid=poll["owner_id"]).json()
    assert winners(outcome) == ["A"]
    assert outcome["num_voters"] == "3"


def test_condorcet_cycle(make_poll, vote, get_outcome):
    poll = make_poll()
    for _ in range(3):
        vote(poll["id"], {"A": 1, "B": 2, "C": 3})
    for _ in range(2):
        vote(poll["id"], {"B": 1, "C": 2, "A": 3})
    for _ in range(2):
        vote(poll["id"], {"C": 1, "A": 2, "B": 3})
    outcome = get_outcome(poll["id"], oid=poll["owner_id"]).json()
    assert outcome["condorcet_winner"] is None
    assert winners(outcome) == ["A"]
    assert outcome["splitting_numbers"] != {}


def test_demo_outcome(client):
    resp = client.post(
        "/polls/demo_outcome",
        json={"rankings": [
            {"num": 2, "ranking": {"A": 1, "B": 2}},
            {"num": 1, "ranking": {"B": 1, "A": 2}},
        ]},
    )
    assert resp.status_code == 200
    assert winners(resp.json()) == ["A"]


# --- private polls ---


def test_private_poll_rejects_vote_without_vid(make_poll, vote):
    poll = make_poll(is_private=True, voter_emails=["a@example.com"])
    assert vote(poll["id"], {"A": 1}, expect_error=True).status_code == 403


def test_private_poll_vid_vote_and_replace(client, make_poll, vote):
    poll = make_poll(is_private=True, voter_emails=["a@example.com"])
    vid = mongo().find_one()["voter_ids"][0]
    vote(poll["id"], {"A": 1, "B": 2}, vid=vid)
    vote(poll["id"], {"B": 1, "A": 2}, vid=vid)  # replaces, not adds
    info = client.get(f"/polls/data/{poll['id']}", params={"oid": poll["owner_id"]}).json()
    assert info["num_ballots"] == 1
    resp = client.get(f"/polls/ranking_information/{poll['id']}", params={"vid": vid})
    assert resp.json()["ranking"] == {"B": 1, "A": 2}


def test_delete_ballot_private(client, make_poll, vote):
    poll = make_poll(is_private=True, voter_emails=["a@example.com"])
    vid = mongo().find_one()["voter_ids"][0]
    vote(poll["id"], {"A": 1}, vid=vid)
    resp = client.request("DELETE", f"/polls/delete_ballot/{poll['id']}", params={"vid": vid})
    assert resp.status_code == 200
    info = client.get(f"/polls/data/{poll['id']}", params={"oid": poll["owner_id"]}).json()
    assert info["num_ballots"] == 0


def test_delete_ballot_public_rejected(client, make_poll, vote):
    poll = make_poll()
    vote(poll["id"], {"A": 1})
    resp = client.request("DELETE", f"/polls/delete_ballot/{poll['id']}", params={"vid": "x"})
    assert resp.status_code == 403


# --- regression tests for the ported fixes ---


def test_regression_ranking_information_unknown_poll(client):
    """The vote page must return a clean not-found (403), not crash with a 500,
    for a valid-format but nonexistent poll id."""
    resp = client.get("/polls/ranking_information/000000000000000000000000")
    assert resp.status_code == 403


def test_regression_result_persists_after_closing(client, make_poll, vote, get_outcome):
    poll = make_poll(candidates=["A", "B"])
    vote(poll["id"], {"A": 1, "B": 2})
    vote(poll["id"], {"B": 1, "A": 2})
    close_poll(client, poll)
    first = get_outcome(poll["id"], oid=poll["owner_id"]).json()
    assert first["is_completed"] is True
    doc = mongo().find_one()
    assert doc["is_completed"] is True and doc["result"] is not None


def test_regression_tiebreak_winner_stable(client, make_poll, vote, get_outcome):
    poll = make_poll(candidates=["A", "B"])
    vote(poll["id"], {"A": 1, "B": 2})
    vote(poll["id"], {"B": 1, "A": 2})
    close_poll(client, poll)
    selected = [get_outcome(poll["id"], oid=poll["owner_id"]).json()["selected_sv_winner"] for _ in range(5)]
    assert selected[0] is not None and all(s == selected[0] for s in selected)


def test_regression_no_voting_after_close(client, make_poll, vote):
    poll = make_poll()
    close_poll(client, poll)
    assert vote(poll["id"], {"A": 1}, expect_error=True).status_code == 403


def test_regression_ballot_rejects_unknown_candidate(client, make_poll, vote, get_outcome):
    """A ballot ranking a nonexistent candidate must be rejected, not brick results."""
    poll = make_poll()
    assert vote(poll["id"], {"Z": 1}, expect_error=True).status_code == 403
    vote(poll["id"], {"A": 1, "B": 2})
    # results still render
    assert get_outcome(poll["id"], oid=poll["owner_id"]).status_code == 200


def test_regression_duplicate_ip_rejected(client, make_poll):
    """Server derives the address; a second ballot from the same client is rejected."""
    poll = make_poll()
    assert client.post(f"/polls/vote/{poll['id']}", json={"ranking": {"A": 1}}).status_code == 200
    assert client.post(f"/polls/vote/{poll['id']}", json={"ranking": {"B": 1}}).status_code == 403
    info = client.get(f"/polls/data/{poll['id']}", params={"oid": poll["owner_id"]}).json()
    assert info["num_ballots"] == 1


def test_regression_client_supplied_ip_ignored(client, make_poll):
    poll = make_poll()
    assert client.post(f"/polls/vote/{poll['id']}", json={"ranking": {"A": 1}, "ip": "1.1.1.1"}).status_code == 200
    assert client.post(f"/polls/vote/{poll['id']}", json={"ranking": {"B": 1}, "ip": "2.2.2.2"}).status_code == 403


def test_regression_outcome_missing_timezone(client, make_poll, vote, get_outcome):
    poll = make_poll()
    vote(poll["id"], {"A": 1, "B": 2})
    mongo().update_one({}, {"$unset": {"timezone": ""}})
    resp = get_outcome(poll["id"], oid=poll["owner_id"])
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "N/A"


def test_submitted_rankings_zero_ballots(client, make_poll):
    poll = make_poll()
    resp = client.get(f"/polls/submitted_rankings/{poll['id']}", params={"oid": poll["owner_id"]})
    assert resp.status_code == 200
    assert resp.json()["num_voters"] == 0


def test_submitted_rankings_requires_owner(client, make_poll):
    poll = make_poll()
    assert client.get(f"/polls/submitted_rankings/{poll['id']}", params={"oid": "wrong"}).status_code == 403
