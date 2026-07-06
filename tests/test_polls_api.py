#
# API tests for poll creation, information, update, and deletion.
#


def test_create_poll_returns_id_and_owner_id(make_poll):
    data = make_poll()
    assert len(data["id"]) == 24
    assert len(data["owner_id"]) == 8


def test_poll_data_as_owner(client, make_poll):
    data = make_poll(title="Owner Poll")
    resp = client.get(f"/polls/data/{data['id']}", params={"oid": data["owner_id"]})
    assert resp.status_code == 200
    info = resp.json()
    assert info["is_owner"] is True
    assert info["title"] == "Owner Poll"
    assert info["candidates"] == ["A", "B", "C"]
    assert info["num_ballots"] == 0


def test_poll_data_unknown_id(client):
    assert client.get("/polls/data/000000000000000000000000").status_code == 403


def test_poll_data_invalid_id(client):
    assert client.get("/polls/data/not-a-valid-id").status_code == 403


def test_update_poll_title(client, make_poll):
    data = make_poll()
    resp = client.post(
        f"/polls/update/{data['id']}", params={"oid": data["owner_id"]}, json={"title": "New Title"}
    )
    assert resp.status_code == 200
    assert client.get(f"/polls/data/{data['id']}").json()["title"] == "New Title"


def test_update_poll_requires_owner(client, make_poll):
    data = make_poll()
    resp = client.post(
        f"/polls/update/{data['id']}", params={"oid": "wrong"}, json={"title": "Hacked"}
    )
    assert resp.status_code == 403


def test_update_invalid_id(client):
    resp = client.post("/polls/update/not-valid", params={"oid": "x"}, json={"title": "t"})
    assert resp.status_code == 403


def test_delete_poll(client, make_poll):
    data = make_poll()
    resp = client.request("DELETE", f"/polls/delete/{data['id']}", params={"oid": data["owner_id"]})
    assert resp.status_code == 200
    assert client.get(f"/polls/data/{data['id']}").status_code == 403


def test_delete_poll_requires_owner(client, make_poll):
    data = make_poll()
    resp = client.request("DELETE", f"/polls/delete/{data['id']}", params={"oid": "wrong"})
    assert resp.status_code == 403


def test_delete_poll_invalid_id(client):
    resp = client.request("DELETE", "/polls/delete/not-valid", params={"oid": "x"})
    assert resp.status_code == 403


def test_private_poll_creates_voter_ids(client, make_poll):
    data = make_poll(is_private=True, voter_emails=["a@example.com", "b@example.com"])
    info = client.get(f"/polls/data/{data['id']}", params={"oid": data["owner_id"]}).json()
    assert info["is_private"] is True
    assert info["num_invited_voters"] == 2
