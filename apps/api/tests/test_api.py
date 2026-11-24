import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def workspace_headers():
    email = f"user-{uuid.uuid4().hex}@example.test"
    password = "Correct-Horse-Battery-42!"
    registered = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert registered.status_code == 200
    token = registered.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/v1/workspaces", headers=auth, json={"name": "Workspace de teste"})
    assert created.status_code == 200
    return {**auth, "X-Workspace-ID": created.json()["id"]}


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


def test_private_resources_require_identity_and_workspace():
    assert client.get("/api/v1/conversations").status_code == 401
    headers = workspace_headers()
    assert client.get("/api/v1/conversations", headers=headers).status_code == 200
    without_workspace = {"Authorization": headers["Authorization"]}
    assert client.get("/api/v1/conversations", headers=without_workspace).status_code == 400


def test_chat_rejects_unknown_provider_after_workspace_auth():
    headers = workspace_headers()
    response = client.post("/api/v1/chat/completions", headers=headers, json={
        "model": "unknown/model",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert response.status_code == 400


def test_chat_rejects_invalid_role():
    headers = workspace_headers()
    response = client.post("/api/v1/chat/completions", headers=headers, json={
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


def test_conversation_persistence_and_workspace_isolation():
    owner_headers = workspace_headers()
    other_headers = workspace_headers()
    created = client.post("/api/v1/conversations", headers=owner_headers,
                          json={"title": "Persistência de teste", "model": "ollama/qwen2.5"})
    assert created.status_code == 200
    conversation_id = created.json()["id"]
    saved = client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=owner_headers,
                        json={"role": "user", "content": "Olá"})
    assert saved.status_code == 200
    history = client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=owner_headers)
    assert history.status_code == 200
    assert history.json()["messages"][0]["content"] == "Olá"
    assert client.get("/api/v1/conversations", headers=other_headers).json()["conversations"] == []
    assert client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/conversations/{conversation_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/conversations/{conversation_id}", headers=owner_headers).json()["deleted"] is True


def test_agent_and_workflow_registry_are_workspace_scoped():
    headers = workspace_headers()
    other = workspace_headers()
    agent = client.post("/api/v1/agents", headers=headers,
                        json={"name": "Assistente de teste", "instructions": "Responda com clareza", "tools": []})
    assert agent.status_code == 200
    assert any(item["id"] == agent.json()["id"] for item in client.get("/api/v1/agents", headers=headers).json()["agents"])
    assert client.get("/api/v1/agents", headers=other).json()["agents"] == []
    workflow = client.post("/api/v1/workflows", headers=headers,
                           json={"name": "Fluxo de teste", "definition": {"nodes": [], "edges": []}})
    assert workflow.status_code == 200
    assert any(item["id"] == workflow.json()["id"] for item in client.get("/api/v1/workflows", headers=headers).json()["workflows"])
    assert client.get("/api/v1/workflows", headers=other).json()["workflows"] == []


def test_register_login_and_workspace_membership():
    email = f"user-{uuid.uuid4().hex[:10]}@example.test"
    password = "Correct-Horse-Battery-42!"
    registered = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert registered.status_code == 200
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    created = client.post("/api/v1/workspaces", headers=headers, json={"name": "Equipe APOLO"})
    assert created.status_code == 200
    listed = client.get("/api/v1/workspaces", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["workspaces"][0]["name"] == "Equipe APOLO"
    assert client.get("/api/v1/workspaces").status_code == 401
    logged_in = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert logged_in.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401


def test_stream_endpoint_requires_provider_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    headers = workspace_headers()
    response = client.post("/api/v1/chat/stream", headers=headers, json={
        "model": "openai/gpt-test", "messages": [{"role": "user", "content": "hello"}]
    })
    assert response.status_code == 503


def test_bounded_agent_execution_and_trace(monkeypatch):
    headers = workspace_headers()
    agent = client.post("/api/v1/agents", headers=headers, json={
        "name": "Agente executor", "instructions": "Resuma com clareza",
        "model": "ollama/test-model", "tools": []
    }).json()

    async def fake_chat(request, http_request):
        return {"choices": [{"message": {"content": "Resultado simulado"}}]}

    monkeypatch.setattr("app.main.chat_completions", fake_chat)
    run = client.post(f"/api/v1/agents/{agent['id']}/run", headers=headers,
                      json={"prompt": "Faça um resumo."})
    assert run.status_code == 200
    assert run.json()["output"] == "Resultado simulado"
    assert run.json()["trace"][0]["status"] == "completed"
    history = client.get("/api/v1/agent-runs", headers=headers)
    assert history.status_code == 200
    assert history.json()["runs"][0]["id"] == run.json()["run_id"]


def test_multi_agent_orchestration_is_bounded(monkeypatch):
    headers = workspace_headers()
    agents = []
    for name in ("Planejador", "Revisor"):
        response = client.post("/api/v1/agents", headers=headers, json={
            "name": name, "instructions": name, "model": "ollama/test-model", "tools": []
        })
        assert response.status_code == 200
        agents.append(response.json()["id"])

    calls = {"count": 0}
    async def fake_chat(request, http_request):
        calls["count"] += 1
        return {"choices": [{"message": {"content": f"Etapa {calls['count']}"}}]}

    monkeypatch.setattr("app.main.chat_completions", fake_chat)
    result = client.post("/api/v1/agents/orchestrate", headers=headers,
                         json={"agent_ids": agents, "prompt": "Planeje e revise.", "max_steps": 2})
    assert result.status_code == 200
    assert calls["count"] == 2
    assert result.json()["trace"][-1]["status"] == "completed"
    too_many = client.post("/api/v1/agents/orchestrate", headers=headers,
                           json={"agent_ids": agents, "prompt": "Teste", "max_steps": 6})
    assert too_many.status_code == 422


def test_workflow_execution_validates_dag_and_runs_model_nodes(monkeypatch):
    headers = workspace_headers()
    definition = {
        "nodes": [
            {"id": "in", "type": "input", "config": {}},
            {"id": "prompt", "type": "prompt", "config": {"instructions": "Analise o pedido."}},
            {"id": "model", "type": "model", "config": {"model": "ollama/test-model"}},
            {"id": "out", "type": "output", "config": {}},
        ],
        "edges": [
            {"source": "in", "target": "prompt"},
            {"source": "prompt", "target": "model"},
            {"source": "model", "target": "out"},
        ],
    }
    saved = client.post("/api/v1/workflows", headers=headers,
                        json={"name": "Fluxo executável", "definition": definition})
    assert saved.status_code == 200

    async def fake_chat(request, http_request):
        assert request.messages[-1].content == "Analise o pedido.\n\nPedido inicial"
        return {"choices": [{"message": {"content": "Resultado do modelo"}}]}

    monkeypatch.setattr("app.main.chat_completions", fake_chat)
    run = client.post(f"/api/v1/workflows/{saved.json()['id']}/run", headers=headers,
                      json={"input": "Pedido inicial"})
    assert run.status_code == 200
    assert run.json()["output"] == "Resultado do modelo"
    history = client.get("/api/v1/workflow-runs", headers=headers)
    assert history.status_code == 200
    assert history.json()["runs"][0]["workflow_id"] == saved.json()["id"]


def test_workflow_execution_rejects_cycles():
    headers = workspace_headers()
    definition = {
        "nodes": [{"id": "in", "type": "input"}, {"id": "a", "type": "prompt"}],
        "edges": [{"source": "in", "target": "a"}, {"source": "a", "target": "in"}],
    }
    saved = client.post("/api/v1/workflows", headers=headers,
                        json={"name": "Fluxo cíclico", "definition": definition})
    response = client.post(f"/api/v1/workflows/{saved.json()['id']}/run", headers=headers,
                           json={"input": "Teste"})
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()


def test_mcp_server_registry_discovery_and_approval_gate(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "tools.example.test")
    headers = workspace_headers()
    other = workspace_headers()
    server = client.post("/api/v1/mcp/servers", headers=headers, json={
        "name": "Servidor de teste", "transport": "streamable-http",
        "endpoint": "https://tools.example.test/mcp"
    })
    assert server.status_code == 200
    server_id = server.json()["id"]
    assert client.get("/api/v1/mcp/servers", headers=other).json()["servers"] == []

    async def fake_discover(transport, endpoint=None, config_key=None):
        assert transport == "streamable-http"
        assert endpoint == "https://tools.example.test/mcp"
        return [{"name": "read_status", "description": "Read-only status", "input_schema": {"type": "object", "properties": {}}}]

    async def fake_call(transport, tool_name, arguments, endpoint=None, config_key=None):
        return {"is_error": False, "content": [{"type": "text", "text": "ok"}], "structured_content": None}

    monkeypatch.setattr("app.main._mcp_discover_tools", fake_discover)
    monkeypatch.setattr("app.main._mcp_invoke_tool", fake_call)
    discovered = client.post(f"/api/v1/mcp/servers/{server_id}/discover", headers=headers)
    assert discovered.status_code == 200
    assert discovered.json()["tools"][0]["approved"] is False

    denied = client.post(f"/api/v1/mcp/servers/{server_id}/tools/read_status/call",
                         headers=headers, json={"arguments": {}})
    assert denied.status_code == 403

    approved = client.post(f"/api/v1/mcp/servers/{server_id}/tools/read_status/approval",
                           headers=headers, json={"approved": True})
    assert approved.status_code == 200
    called = client.post(f"/api/v1/mcp/servers/{server_id}/tools/read_status/call",
                         headers=headers, json={"arguments": {}})
    assert called.status_code == 200
    assert called.json()["content"][0]["text"] == "ok"
    assert client.get(f"/api/v1/mcp/servers/{server_id}/tools", headers=other).status_code == 404


def test_mcp_http_endpoint_requires_admin_allowlist(monkeypatch):
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    headers = workspace_headers()
    response = client.post("/api/v1/mcp/servers", headers=headers, json={
        "name": "Not trusted", "transport": "streamable-http",
        "endpoint": "https://untrusted.example/mcp"
    })
    assert response.status_code == 400
    assert "allowlist" in response.json()["detail"].lower()


def test_mcp_stdio_requires_admin_configured_alias(monkeypatch):
    monkeypatch.setenv("MCP_STDIO_SERVERS_JSON", "{}")
    headers = workspace_headers()
    response = client.post("/api/v1/mcp/servers", headers=headers, json={
        "name": "Unknown stdio", "transport": "stdio", "config_key": "untrusted-command"
    })
    assert response.status_code == 400


def test_mcp_bearer_credentials_are_encrypted_and_hidden(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("APOLO_MCP_ENCRYPTION_KEY", key)
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "secure-tools.example.test")
    headers = workspace_headers()
    raw_token = "mcp-secret-token-value"
    response = client.post("/api/v1/mcp/servers", headers=headers, json={
        "name": "Secure MCP", "transport": "streamable-http",
        "endpoint": "https://secure-tools.example.test/mcp", "bearer_token": raw_token
    })
    assert response.status_code == 200
    server_id = response.json()["id"]
    listed = client.get("/api/v1/mcp/servers", headers=headers)
    assert "auth_ciphertext" not in listed.json()["servers"][0]
    assert raw_token not in listed.text
    with __import__("app.main", fromlist=["_db"])._db() as conn:
        row = conn.execute("SELECT auth_ciphertext FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
    assert row["auth_ciphertext"] != raw_token
    assert __import__("app.main", fromlist=["_mcp_decrypt_secret"])._mcp_decrypt_secret(row["auth_ciphertext"]) == raw_token

    rotated = client.post(f"/api/v1/mcp/servers/{server_id}/credentials", headers=headers,
                          json={"bearer_token": "rotated-secret"})
    assert rotated.status_code == 200
    assert rotated.json()["credential_configured"] is True
    revoked = client.delete(f"/api/v1/mcp/servers/{server_id}/credentials", headers=headers)
    assert revoked.status_code == 200
    with __import__("app.main", fromlist=["_db"])._db() as conn:
        row = conn.execute("SELECT auth_ciphertext FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
    assert row["auth_ciphertext"] is None
