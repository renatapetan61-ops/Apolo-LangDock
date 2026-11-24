import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


def test_conversation_persistence_and_delete():
    created = client.post("/api/v1/conversations", json={"title":"Persistência de teste","model":"ollama/qwen2.5"})
    assert created.status_code == 200
    conversation_id = created.json()["id"]
    saved = client.post(f"/api/v1/conversations/{conversation_id}/messages", json={"role":"user","content":"Olá"})
    assert saved.status_code == 200
    history = client.get(f"/api/v1/conversations/{conversation_id}/messages")
    assert history.status_code == 200
    assert history.json()["messages"][0]["content"] == "Olá"
    assert client.delete(f"/api/v1/conversations/{conversation_id}").json()["deleted"] is True

def test_agent_and_workflow_registry():
    agent = client.post("/api/v1/agents", json={"name":"Assistente de teste","instructions":"Responda com clareza","tools":[]})
    assert agent.status_code == 200
    assert any(item["id"] == agent.json()["id"] for item in client.get("/api/v1/agents").json()["agents"])
    workflow = client.post("/api/v1/workflows", json={"name":"Fluxo de teste","definition":{"nodes":[],"edges":[]}})
    assert workflow.status_code == 200
    assert any(item["id"] == workflow.json()["id"] for item in client.get("/api/v1/workflows").json()["workflows"])


def test_register_login_and_workspace_membership():
    email = f"user-{__import__('uuid').uuid4().hex[:10]}@example.test"
    password = "Correct-Horse-Battery-42!"
    registered = client.post("/api/v1/auth/register", json={"email":email,"password":password})
    assert registered.status_code == 200
    token = registered.json()["access_token"]
    headers = {"Authorization":f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    created = client.post("/api/v1/workspaces", headers=headers, json={"name":"Equipe APOLO"})
    assert created.status_code == 200
    listed = client.get("/api/v1/workspaces", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["workspaces"][0]["name"] == "Equipe APOLO"
    assert client.get("/api/v1/workspaces").status_code == 401
    logged_in = client.post("/api/v1/auth/login", json={"email":email,"password":password})
    assert logged_in.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email":email,"password":"wrong-password"}).status_code == 401

def test_stream_endpoint_requires_provider_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/api/v1/chat/stream", json={"model":"openai/gpt-test","messages":[{"role":"user","content":"hello"}]})
    assert response.status_code == 503
