from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_client(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    settings = Settings(database_url=database_url, cors_origins="http://localhost:5173")
    return TestClient(create_app(settings))


def test_health_and_item_lifecycle(tmp_path):
    with make_client(tmp_path) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        created = client.post("/api/v1/items", json={"title": "完成接口联调"})
        assert created.status_code == 201
        item = created.json()
        assert item["title"] == "完成接口联调"
        assert item["completed"] is False
        assert item["created_at"].endswith(("Z", "+00:00"))

        listed = client.get("/api/v1/items")
        assert listed.status_code == 200
        assert [entry["id"] for entry in listed.json()] == [item["id"]]

        updated = client.put(f"/api/v1/items/{item['id']}", json={"completed": True})
        assert updated.status_code == 200
        assert updated.json()["completed"] is True

        deleted = client.delete(f"/api/v1/items/{item['id']}")
        assert deleted.status_code == 204
        assert client.get("/api/v1/items").json() == []


def test_item_validation_and_missing_item(tmp_path):
    with make_client(tmp_path) as client:
        blank = client.post("/api/v1/items", json={"title": "   "})
        assert blank.status_code == 422

        normalized = client.post("/api/v1/items", json={"title": "  自动去除空格  "})
        assert normalized.status_code == 201
        assert normalized.json()["title"] == "自动去除空格"

        extra_create_field = client.post(
            "/api/v1/items",
            json={"title": "有效标题", "surprise": True},
        )
        assert extra_create_field.status_code == 422

        invalid_id = client.put("/api/v1/items/0", json={"completed": True})
        assert invalid_id.status_code == 422

        non_boolean = client.put("/api/v1/items/999", json={"completed": 1})
        assert non_boolean.status_code == 422

        extra_update_field = client.put(
            "/api/v1/items/999",
            json={"completed": True, "surprise": True},
        )
        assert extra_update_field.status_code == 422

        missing = client.put("/api/v1/items/999", json={"completed": True})
        assert missing.status_code == 404

        invalid_delete_id = client.delete("/api/v1/items/0")
        assert invalid_delete_id.status_code == 422

        missing_delete = client.delete("/api/v1/items/999")
        assert missing_delete.status_code == 404
