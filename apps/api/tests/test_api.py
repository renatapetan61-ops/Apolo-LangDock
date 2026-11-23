from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_provider_catalog_never_claims_paid_apis_are_free():
    providers = client.get("/api/v1/providers").json()["providers"]
    by_id = {item["id"]: item for item in providers}
    assert by_id["openai"]["configured"] in (True, False)
    assert "billing" in by_id["openai"]["free_policy"].lower()
    assert "billing" in by_id["anthropic"]["free_policy"].lower()


def test_chat_rejects_unknown_provider():
    response = client.post("/api/v1/chat/completions", json={
        "model": "unknown/model",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert response.status_code == 400


def test_chat_rejects_invalid_role():
    response = client.post("/api/v1/chat/completions", json={
        "model": "ollama/llama3.2",
        "messages": [{"role": "tool", "content": "hello"}],
    })
    assert response.status_code == 422


def test_live_model_discovery_uses_provider_adapter(monkeypatch):
    async def fake_discover(provider: str):
        if provider == "ollama":
            return [{"id": "ollama/qwen2.5", "provider": "ollama", "label": "qwen2.5", "free": True, "availability": "local"}]
        return []

    monkeypatch.setattr("app.main._discover", fake_discover)
    response = client.get("/api/v1/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["discovery"] == "live"
    assert any(model["id"] == "ollama/qwen2.5" for model in payload["models"])
