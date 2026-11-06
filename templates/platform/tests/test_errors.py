from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.platform.errors import Problem, install_error_handlers, not_signed_in


class Body(BaseModel):
    name: str


def make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/problem")
    def problem():
        raise Problem(
            "lesson_has_blockers",
            "Not ready.",
            409,
            field="doc",
            extra={"issues": [1]},
            headers={"Retry-After": "5"},
        )

    @app.get("/signed-out")
    def signed_out():
        raise not_signed_in()

    @app.post("/validate")
    def validate(body: Body):
        return body

    return app


def test_problem_shape_and_order():
    app = make_app()
    install_error_handlers(app)
    response = TestClient(app).get("/problem")
    assert response.status_code == 409
    assert response.headers["retry-after"] == "5"
    assert list(response.json()["detail"]) == ["code", "message", "issues", "field"]
    assert response.json() == {
        "detail": {
            "code": "lesson_has_blockers",
            "message": "Not ready.",
            "issues": [1],
            "field": "doc",
        }
    }


def test_not_signed_in_is_byte_identical_to_the_monolith():
    app = make_app()
    install_error_handlers(app)
    response = TestClient(app).get("/signed-out")
    assert response.status_code == 401
    assert response.content == (
        b'{"detail":{"code":"not_signed_in","message":"Please sign in to continue."}}'
    )


def test_validation_errors_keep_fastapis_shape():
    plain, ours = make_app(), make_app()
    install_error_handlers(ours)
    expected = TestClient(plain).post("/validate", json={"name": 3})
    got = TestClient(ours).post("/validate", json={"name": 3})
    assert got.status_code == expected.status_code == 422
    assert got.content == expected.content
