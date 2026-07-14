"""FT-M1: admin auth, refresh rotation/reuse, RBAC."""


async def test_login_ok_sets_refresh_cookie(client, admin):
    response = await client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "Passw0rd!123"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert set(data["roles"]) == {"hr_admin", "test_creator", "evaluator"}
    assert "tb_refresh" in response.headers.get("set-cookie", "")


async def test_login_bad_credentials_401(client, admin):
    response = await client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_refresh_rotates_and_reuse_revokes_family(client, admin):
    """FT-M1-02 / UT-M1-03: rotated token works once; replaying the old one kills
    the whole family."""
    login = await client.post(
        "/api/v1/auth/admin/login",
        json={"email": "admin@example.com", "password": "Passw0rd!123"},
    )
    first_refresh = login.json()["data"]["refresh_token"]

    rotated = await client.post(
        "/api/v1/auth/admin/refresh", json={"refresh_token": first_refresh}
    )
    assert rotated.status_code == 200
    second_refresh = rotated.json()["data"]["refresh_token"]

    replay = await client.post(
        "/api/v1/auth/admin/refresh", json={"refresh_token": first_refresh}
    )
    assert replay.status_code == 401

    # family revoked: even the newest token no longer works
    after_reuse = await client.post(
        "/api/v1/auth/admin/refresh", json={"refresh_token": second_refresh}
    )
    assert after_reuse.status_code == 401


async def test_rbac_evaluator_cannot_create_questions(client, evaluator_only):
    response = await client.post(
        "/api/v1/questions",
        json={"qtype": "mcq", "title": "blocked question", "config": {}},
        headers=evaluator_only["headers"],
    )
    assert response.status_code == 403


async def test_rbac_evaluator_cannot_manage_users(client, evaluator_only):
    response = await client.get("/api/v1/admin/users", headers=evaluator_only["headers"])
    assert response.status_code == 403


async def test_unauthenticated_401(client):
    response = await client.get("/api/v1/questions")
    assert response.status_code == 401


async def test_candidate_token_rejected_on_admin_routes(client, admin):
    from tests.conftest import add_candidate, build_published_assessment, candidate_login

    assessment = await build_published_assessment(client, admin, with_coding=False)
    assignment = await add_candidate(client, admin, assessment["id"])
    headers = await candidate_login(client, assignment)
    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 403
