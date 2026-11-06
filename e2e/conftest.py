"""Fixtures for the end-to-end suite: the whole compose stack, through the gateway only.

Everything goes to the gateway (E2E_BASE_URL, default http://localhost:8000) and Mailpit's
API (E2E_MAILPIT_URL, default http://localhost:8025). The one exception is
test_auth.py's check that a service refuses a request that did not come through the
gateway, which calls the services' own host ports on purpose.

The stack must be up and seeded first: scripts/e2e.sh does both, then runs this suite.
Every account the suite creates has a fresh email, and every topic a fresh name, so it can
be run again and again without resetting anything.
"""

import contextlib
import os
import re
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from shapes import check

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
MAILPIT_URL = os.environ.get("E2E_MAILPIT_URL", "http://localhost:8025")
# How long to wait for something that crosses the broker (publish, erase, email).
EVENTUAL_SECONDS = float(os.environ.get("E2E_EVENTUAL_SECONDS", "15"))

ADMIN = {"email": "admin@sgjio.example.com", "password": "AdminPass123"}
NEWCOMER = {"email": "newcomer@sgjio.example.com", "password": "UserPass123"}
PASSWORD = "E2ePass123"


def unique(prefix: str = "e2e") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def unique_email(domain: str = "example.com") -> str:
    return f"{unique()}@{domain}"


def eventually(
    probe: Callable[[], Any], what: str, timeout: float = EVENTUAL_SECONDS, every: float = 0.25
) -> Any:
    """Call `probe` until it returns something truthy, and return that. Fails after
    `timeout` seconds with `what` (replication across the broker is usually under 1 s)."""
    deadline = time.monotonic() + timeout
    last: Any = None
    while True:
        try:
            last = probe()
        except AssertionError as error:
            last = error
        else:
            if last:
                return last
        if time.monotonic() >= deadline:
            pytest.fail(f"timed out after {timeout:.0f}s waiting for {what} (last: {last!r})")
        time.sleep(every)


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=False)


# --- The stack --------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def stack_is_up() -> None:
    try:
        health = httpx.get(f"{BASE_URL}/api/health", timeout=5)
        mailpit = httpx.get(f"{MAILPIT_URL}/api/v1/info", timeout=5)
    except httpx.HTTPError as error:
        pytest.exit(f"The stack is not reachable ({error}). Run scripts/e2e.sh.", returncode=2)
    if health.status_code != 200 or mailpit.status_code != 200:
        pytest.exit("The gateway or Mailpit is not healthy. Run scripts/e2e.sh.", returncode=2)
    with client() as http:
        if http.post("/api/admin/auth/sign-in", json=ADMIN).status_code != 200:
            pytest.exit("The seed admin can't sign in: run scripts/seed-all.sh.", returncode=2)


# --- Signed-in clients ------------------------------------------------------------------


def sign_in_admin(email: str = ADMIN["email"], password: str = ADMIN["password"]) -> httpx.Client:
    http = client()
    response = http.post("/api/admin/auth/sign-in", json={"email": email, "password": password})
    check(response, "POST /api/admin/auth/sign-in", 200)
    return http


@pytest.fixture
def admin() -> Iterator[httpx.Client]:
    http = sign_in_admin()
    yield http
    http.close()


def register(
    http: httpx.Client, email: str, *, user_type: str = "newcomer", name: str = "E2E Learner"
) -> dict:
    version = check(
        http.get("/api/auth/privacy-notice-version"), "GET /api/auth/privacy-notice-version", 200
    )
    response = http.post(
        "/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
            "user_type": user_type,
            "privacy_consent": True,
            "privacy_notice_version": version["version"],
        },
    )
    return check(response, "POST /api/auth/register", 201)


def onboard(http: httpx.Client) -> None:
    """Finish the introduction and save a profile, as a new learner's first pages do."""
    check(http.post("/api/intro/finished"), "POST /api/intro/finished", 200)
    check(
        http.put(
            "/api/profile",
            json={"neighbourhood": "Tampines", "interests": ["Food"], "languages": ["English"]},
        ),
        "PUT /api/profile",
        200,
    )


class Learner:
    def __init__(self, http: httpx.Client, email: str, user: dict):
        self.http, self.email, self.user = http, email, user

    @property
    def id(self) -> str:
        return self.user["id"]


@pytest.fixture
def new_learner() -> Iterator[Callable[..., Learner]]:
    """Register fresh learners (signed in, introduction finished, profile saved)."""
    made: list[httpx.Client] = []

    def make(*, user_type: str = "newcomer", onboarded: bool = True) -> Learner:
        http = client()
        made.append(http)
        email = unique_email()
        body = register(http, email, user_type=user_type)
        if onboarded:
            onboard(http)
        return Learner(http, email, body["user"])

    yield make
    for http in made:
        http.close()


# --- Mailpit ------------------------------------------------------------------------------


class Mailpit:
    def __init__(self):
        self.http = httpx.Client(base_url=MAILPIT_URL, timeout=10)

    def messages_to(self, address: str) -> list[dict]:
        response = self.http.get("/api/v1/search", params={"query": f'to:"{address}"'})
        response.raise_for_status()
        return response.json()["messages"]

    def wait_for(self, address: str, subject_contains: str = "", count: int = 1) -> dict:
        """The newest email to `address` (whose subject contains the text), once at least
        `count` such emails have arrived. Returns the full message (Text, HTML, ...)."""

        def probe():
            found = [
                message
                for message in self.messages_to(address)
                if subject_contains.lower() in message["Subject"].lower()
            ]
            return found if len(found) >= count else None

        found = eventually(probe, f"an email to {address} ({subject_contains!r})")
        newest = max(found, key=lambda message: message["Created"])
        response = self.http.get(f"/api/v1/message/{newest['ID']}")
        response.raise_for_status()
        return response.json()

    @staticmethod
    def link(message: dict, page: str) -> str:
        """The first link to `page` (e.g. "/reset-password") in the email's text."""
        match = re.search(
            rf"https?://[^\s\"'<>]*{re.escape(page)}\?token=[\w\-.~%]+", message["Text"]
        )
        assert match, f"no {page} link in:\n{message['Text']}"
        return match.group(0)

    @staticmethod
    def token(link: str) -> str:
        return link.split("token=", 1)[1]


@pytest.fixture(scope="session")
def mailpit() -> Iterator[Mailpit]:
    box = Mailpit()
    yield box
    box.http.close()


# --- Content the suite authors ------------------------------------------------------------


def lesson_doc(questions: int = 2, *, image: dict | None = None, words: str = "") -> dict:
    """A small lesson that can be published: an intro card, then `questions` scored ones
    whose options have ids "q<n>-right" and "q<n>-wrong" (ids are unique per lesson)."""
    cards: list[dict] = [{"id": "intro", "text": f"Welcome to this lesson. {words}".strip()}]
    if image:
        cards[0]["image"] = image
    for n in range(questions):
        cards.append(
            {
                "id": f"card{n}",
                "text": f"Question {n + 1}: pick {{{{blank}}}}.",
                "question": {
                    "id": f"q{n}",
                    "options": [
                        {"id": f"q{n}-right", "text": "Right", "correct": True},
                        {"id": f"q{n}-wrong", "text": "Wrong", "why_not": "Not this one."},
                    ],
                    "explanation": "Because it is right.",
                },
            }
        )
    return {"cards": cards}


def create_topic(admin: httpx.Client, name: str | None = None) -> dict:
    response = admin.post(
        "/api/admin/topics", json={"name": name or unique("E2E topic"), "description": "e2e"}
    )
    return check(response, "POST /api/admin/topics", 201)


def create_lesson(admin: httpx.Client, topic_id: str, *, level: int = 1, **doc_args) -> dict:
    response = admin.post(
        "/api/admin/lessons",
        json={
            "title": unique("E2E lesson"),
            "summary": "An e2e lesson.",
            "topic_id": topic_id,
            "level": level,
            "doc": lesson_doc(**doc_args),
        },
    )
    return check(response, "POST /api/admin/lessons", 201)


def publish(admin: httpx.Client, lesson: dict) -> dict:
    response = admin.post(
        f"/api/admin/lessons/{lesson['id']}/publish", json={"updated_at": lesson["updated_at"]}
    )
    return check(response, "POST /api/admin/lessons/{lesson_id}/publish", 200)


def archive_topic(admin: httpx.Client, topic_id: str) -> None:
    check(
        admin.post(f"/api/admin/topics/{topic_id}/archive"),
        "POST /api/admin/topics/{topic_id}/archive",
        200,
    )


@pytest.fixture
def scratch_topics(admin: httpx.Client) -> Iterator[list[str]]:
    """Topic ids to tidy away when the test ends, pass or fail, so the suite's topics never
    show up for learners or in the aptitude test afterwards, and leave nothing on the
    admin portal's to-do lists of a stack the team demos from."""
    ids: list[str] = []
    yield ids
    if ids:
        tidy_away(admin, set(ids))


def tidy_away(admin: httpx.Client, topic_ids: set[str]) -> None:
    """Dismiss the open reports on these topics' lessons, deactivate their aptitude
    questions (questions can't be deleted), then archive the topics. Best effort: a
    failure here must not hide the test's own result."""
    with contextlib.suppress(httpx.HTTPError):
        lessons = admin.get("/api/admin/lessons")
        lesson_ids = {
            lesson["id"]
            for lesson in (lessons.json() if lessons.status_code == 200 else [])
            if lesson["topic_id"] in topic_ids
        }
        reports = admin.get("/api/admin/reports")
        for report in reports.json() if reports.status_code == 200 else []:
            if report["lesson_id"] in lesson_ids:
                admin.put(f"/api/admin/reports/{report['id']}/status", json={"status": "dismissed"})
        bank = admin.get("/api/admin/aptitude-questions")
        for question in bank.json()["questions"] if bank.status_code == 200 else []:
            if question["topic_id"] in topic_ids and question["is_active"]:
                admin.patch(
                    f"/api/admin/aptitude-questions/{question['id']}", json={"is_active": False}
                )
    for topic_id in topic_ids:
        with contextlib.suppress(httpx.HTTPError):
            admin.post(f"/api/admin/topics/{topic_id}/archive")


def learner_sees(http: httpx.Client, lesson_id: str) -> dict | None:
    response = http.get(f"/api/lessons/{lesson_id}")
    if response.status_code == 404:
        return None
    return check(response, "GET /api/lessons/{lesson_id}", 200)


def take_lesson(http: httpx.Client, lesson_id: str, *, right: bool = True) -> dict:
    """Run through a published lesson as a learner: start, answer every question, finish."""
    lesson = check(http.get(f"/api/lessons/{lesson_id}"), "GET /api/lessons/{lesson_id}", 200)
    attempt = check(
        http.post(f"/api/lessons/{lesson_id}/attempts", json={"version": lesson["version"]}),
        "POST /api/lessons/{lesson_id}/attempts",
        201,
    )
    for card in lesson["cards"]:
        question = card["question"]
        if question is None:
            continue
        ids = [option["id"] for option in question["options"]]
        wanted = "-right" if right else "-wrong"
        # The suite's own lessons say which is which; for any other, take the first option.
        option = next((i for i in ids if i.endswith(wanted)), ids[0])
        result = check(
            http.post(
                f"/api/attempts/{attempt['id']}/answers",
                json={"question_id": question["id"], "option_id": option},
            ),
            "POST /api/attempts/{attempt_id}/answers",
            200,
        )
        assert result["correct"] is (option == result["correct_option_id"])
    return check(
        http.post(f"/api/attempts/{attempt['id']}/finish"),
        "POST /api/attempts/{attempt_id}/finish",
        200,
    )


def progress(http: httpx.Client) -> dict:
    return check(http.get("/api/progress"), "GET /api/progress", 200)


def circle(http: httpx.Client, topic_id: str) -> dict | None:
    return next((t for t in progress(http)["topics"] if t["id"] == topic_id), None)
