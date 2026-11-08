import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.platform.principal import Principal, require_principal
from app.platform.testing import admin_headers, app_headers, headers_for

NOT_SIGNED_IN = {"detail": {"code": "not_signed_in", "message": "Please sign in to continue."}}


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/app")
    def app_route(principal: Principal = Depends(require_principal("app"))):
        return {
            "id": str(principal.user_id),
            "type": principal.user_type,
            "profile": principal.profile_completed,
            "role": principal.role,
        }

    @app.get("/admin")
    def admin_route(principal: Principal = Depends(require_principal("admin"))):
        return {"id": str(principal.user_id), "type": principal.user_type}

    from app.platform.errors import install_error_handlers

    install_error_handlers(app)
    return TestClient(app)


def test_app_principal(client):
    user_id = uuid.uuid4()
    response = client.get("/app", headers=app_headers(user_id, "singaporean", False))
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user_id),
        "type": "singaporean",
        "profile": False,
        "role": "user",
    }


def test_admin_principal_has_no_user_type(client):
    user_id = uuid.uuid4()
    response = client.get("/admin", headers=admin_headers(user_id))
    assert response.json() == {"id": str(user_id), "type": None}


def _with(headers: dict, **changes) -> dict:
    headers = dict(headers)
    for name, value in changes.items():
        name = name.replace("_", "-")
        if value is None:
            headers.pop(name, None)
        else:
            headers[name] = value
    return headers


@pytest.mark.parametrize(
    "path,headers",
    [
        ("/app", {}),  # no headers at all
        ("/app", _with(app_headers(), **{"X_Gateway_Key": None})),  # bypassed the gateway
        ("/app", _with(app_headers(), **{"X_Gateway_Key": "wrong"})),
        ("/app", _with(app_headers(), **{"X_User_Id": "not-a-uuid"})),
        ("/app", _with(app_headers(), **{"X_User_Role": "superuser"})),
        ("/app", admin_headers()),  # admin session on an app route
        ("/admin", app_headers()),  # app session on an admin route
        ("/admin", headers_for(Principal(uuid.uuid4(), "admin", "user", None, False))),
    ],
)
def test_refused(client, path, headers):
    response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert response.json() == NOT_SIGNED_IN


def test_empty_gateway_key_refuses_everything(client):
    from app.platform.config import configure

    configure(gateway_key="")
    response = client.get("/app", headers=app_headers() | {"X-Gateway-Key": ""})
    assert response.status_code == 401
