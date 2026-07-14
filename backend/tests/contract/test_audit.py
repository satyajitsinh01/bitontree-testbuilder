"""FT-M1-04/05: audit log filtering and immutability surface."""


async def test_sensitive_actions_produce_audit_entries(client, admin):
    from tests.conftest import add_candidate, build_published_assessment

    assessment = await build_published_assessment(client, admin, with_coding=False)
    await add_candidate(client, admin, assessment["id"])

    response = await client.get("/api/v1/admin/audit-logs", headers=admin["headers"])
    assert response.status_code == 200
    actions = {item["action"] for item in response.json()["data"]["items"]}
    assert "assessment.created" in actions
    assert "assessment.published" in actions
    assert "assignment.created" in actions


async def test_audit_filter_by_action(client, admin):
    from tests.conftest import build_published_assessment

    await build_published_assessment(client, admin, with_coding=False)
    response = await client.get(
        "/api/v1/admin/audit-logs",
        params={"action": "assessment.published"},
        headers=admin["headers"],
    )
    items = response.json()["data"]["items"]
    assert items and all(i["action"] == "assessment.published" for i in items)


async def test_no_mutation_route_exists_for_audit_logs(client, admin):
    """FT-M1-04: immutability — no update/delete endpoint is even routed."""
    for method in ("patch", "delete", "put"):
        response = await getattr(client, method)(
            "/api/v1/admin/audit-logs/any-id", headers=admin["headers"]
        )
        assert response.status_code in (404, 405)
