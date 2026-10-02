"""The signed-in user's own profile: interests, languages and neighbourhood (SCRUM-14).

Like progress, there is no user id in the path, so a user can only read or change their
own profile. What other users may see for buddy matching (AC5) is a separate, narrower
shape that Module 2 adds; nothing here is shown to anyone else.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.db import get_db
from app.models import Profile, User
from app.profile_options import INTERESTS, LANGUAGES, NEIGHBOURHOODS
from app.schemas import ProfileIn, ProfileOptionsOut, ProfileOut

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/profile/options", response_model=ProfileOptionsOut)
def get_profile_options() -> ProfileOptionsOut:
    """The choices the profile form offers."""
    return ProfileOptionsOut(
        interests=INTERESTS, languages=LANGUAGES, neighbourhoods=NEIGHBOURHOODS
    )


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: User = Depends(require_user)) -> ProfileOut:
    """Shown in Settings (SCRUM-14 AC3, SCRUM-41 AC3) and used to prefill the editor."""
    return ProfileOut.model_validate(user.profile) if user.profile else ProfileOut()


@router.put(
    "/profile",
    response_model=ProfileOut,
    responses={422: {"description": "A field is empty or holds a value not on the list"}},
)
def save_profile(
    body: ProfileIn, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> ProfileOut:
    """Create or replace the profile, from onboarding or from Settings (AC1, AC4)."""
    if user.profile is None:
        user.profile = Profile()
    user.profile.interests = body.interests
    user.profile.languages = body.languages
    user.profile.neighbourhood = body.neighbourhood
    db.commit()
    return ProfileOut.model_validate(user.profile)
