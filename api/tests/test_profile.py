"""SCRUM-14: setting up and editing the profile used for recommendations and matching."""

from sqlalchemy import select

from app.models import Profile

PROFILE = {
    "interests": ["Food", "Music"],
    "languages": ["English", "Mandarin"],
    "neighbourhood": "Tampines",
}


def _sign_in(client, make_user, email="user@example.com"):
    make_user(email=email)
    client.post("/api/auth/sign-in", json={"email": email, "password": "Password123"})


def test_profile_needs_a_signed_in_user(client):
    assert client.get("/api/profile").status_code == 401
    assert client.put("/api/profile", json=PROFILE).status_code == 401
    assert client.get("/api/profile/options").status_code == 401


def test_options_list_every_choice(client, make_user):
    _sign_in(client, make_user)
    options = client.get("/api/profile/options").json()
    assert "Food" in options["interests"]
    assert "English" in options["languages"]
    assert "Tampines" in options["neighbourhoods"]


def test_a_new_user_has_an_empty_profile(client, make_user):
    _sign_in(client, make_user)
    assert client.get("/api/profile").json() == {
        "interests": [],
        "languages": [],
        "neighbourhood": None,
    }


def test_saving_a_complete_profile(client, make_user, db):
    # AC1, AC3
    _sign_in(client, make_user)
    response = client.put("/api/profile", json=PROFILE)
    assert response.status_code == 200
    assert response.json() == PROFILE
    assert client.get("/api/profile").json() == PROFILE
    assert db.scalar(select(Profile)).neighbourhood == "Tampines"


def test_editing_replaces_the_saved_profile(client, make_user):
    # AC4
    _sign_in(client, make_user)
    client.put("/api/profile", json=PROFILE)
    changed = {"interests": ["Hiking and nature"], "languages": ["Malay"], "neighbourhood": "Bedok"}
    assert client.put("/api/profile", json=changed).json() == changed
    assert client.get("/api/profile").json() == changed


def test_each_missing_field_is_named(client, make_user):
    # AC2: the form highlights the field that is incomplete.
    _sign_in(client, make_user)
    response = client.put("/api/profile", json={"interests": [], "languages": []})
    assert response.status_code == 422
    messages = {item["loc"][-1]: item["msg"] for item in response.json()["detail"]}
    assert messages["interests"].endswith("Select at least one interest.")
    assert messages["languages"].endswith("Select at least one language you speak.")
    assert messages["neighbourhood"].endswith("Select your neighbourhood.")


def test_values_off_the_list_are_refused(client, make_user):
    _sign_in(client, make_user)
    response = client.put("/api/profile", json={**PROFILE, "neighbourhood": "Atlantis"})
    assert response.status_code == 422
    response = client.put("/api/profile", json={**PROFILE, "interests": ["Food", "Juggling"]})
    assert response.status_code == 422


def test_repeated_choices_are_saved_once(client, make_user):
    _sign_in(client, make_user)
    response = client.put("/api/profile", json={**PROFILE, "languages": ["English", "English"]})
    assert response.json()["languages"] == ["English"]


def test_users_only_see_their_own_profile(client, make_user):
    _sign_in(client, make_user)
    client.put("/api/profile", json=PROFILE)
    client.post("/api/auth/sign-out")
    _sign_in(client, make_user, email="other@example.com")
    assert client.get("/api/profile").json()["interests"] == []
