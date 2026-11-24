from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

APP_VERSION = "0.3.0"
app = FastAPI(title="APOLO LangDock API", version=APP_VERSION, description="Open AI workspace API. Provider quotas and pricing are controlled by upstream providers.")
origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])

PROVIDER_INFO = {
    "openrouter": ("OpenRouter", "Selected free routes; quotas and availability vary."),
    "google": ("Google AI", "Selected models may have limited free quota; region and terms apply."),
    "openai": ("OpenAI", "API billing may apply; check the account and model price."),
    "anthropic": ("Anthropic", "API billing may apply; check the account and model price."),
    "ollama": ("Ollama (local)", "Local inference; hardware and electricity are the user's responsibility."),
}

class ChatMessage(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, value: str) -> str:
        if value not in {"system", "user", "assistant"}:
            raise ValueError("role must be system, user, or assistant")
        return value

class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=1024, ge=1, le=32768)

def _key(provider: str) -> str | None:
    return {"openrouter": os.getenv("OPENROUTER_API_KEY"), "google": os.getenv("GOOGLE_API_KEY"), "openai": os.getenv("OPENAI_API_KEY"), "anthropic": os.getenv("ANTHROPIC_API_KEY")}.get(provider)

def _configured(provider: str) -> bool:
    return bool(_key(provider)) if provider != "ollama" else True

def _model(provider: str, model_id: str, label: str, free: bool | None = None) -> dict[str, Any]:
    return {"id": f"{provider}/{model_id}", "provider": provider, "label": label or model_id, "free": free, "availability": "local" if provider == "ollama" else ("free-route" if free else "provider-quota-or-billing")}

async def _get_json(url: str, headers: dict[str, str] | None = None, params: dict[str, str] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, headers=headers, params=params)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"provider_error": response.text[:1000], "status": response.status_code})
    return response.json()

async def _discover(provider: str) -> list[dict[str, Any]]:
    key = _key(provider)
    if provider != "ollama" and not key:
        return []
    try:
        if provider == "openrouter":
            data = await _get_json("https://openrouter.ai/api/v1/models", {"Authorization": f"Bearer {key}"})
            found = []
            for item in data.get("data", []):
                pricing = item.get("pricing", {})
                is_free = float(pricing.get("prompt", -1) or 0) == 0 and float(pricing.get("completion", -1) or 0) == 0
                found.append(_model(provider, item["id"], item.get("name") or item["id"], is_free))
            return found
        if provider == "google":
            data = await _get_json("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key or ""})
            return [_model(provider, item["name"].removeprefix("models/"), item.get("displayName") or item["name"]) for item in data.get("models", []) if "generateContent" in item.get("supportedGenerationMethods", [])]
        if provider == "ollama":
            base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1").removesuffix("/v1")
            data = await _get_json(f"{base}/api/tags")
            return [_model(provider, item["name"], item.get("details", {}).get("family") or item["name"], True) for item in data.get("models", [])]
        if provider == "openai":
            data = await _get_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
            return [_model(provider, item["id"], item["id"]) for item in data.get("data", []) if any(token in item["id"] for token in ("gpt-", "o1", "o3", "o4"))]
        if provider == "anthropic":
            data = await _get_json("https://api.anthropic.com/v1/models", {"x-api-key": key or "", "anthropic-version": "2023-06-01"})
            return [_model(provider, item["id"], item.get("display_name") or item["id"]) for item in data.get("data", [])]
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return []
    return []

async def _post_openai_compatible(base_url: str, key: str | None, model: str, body: dict[str, Any]) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json={**body, "model": model})
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"provider_error": response.text[:1200], "status": response.status_code})
    return response.json()

@app.get("/")
async def root():
    return {"name": "APOLO LangDock API", "version": APP_VERSION, "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "apolo-langdock-api", "version": APP_VERSION}

@app.get("/api/v1/providers")
async def providers():
    return {"providers": [{"id": key, "name": name, "configured": _configured(key), "free_policy": policy} for key, (name, policy) in PROVIDER_INFO.items()]}

@app.get("/api/v1/models")
async def models(refresh: bool = False):
    # Discovery is live and only queries providers for which server-side credentials exist.
    discovered: list[dict[str, Any]] = []
    errors: list[str] = []
    for provider in PROVIDER_INFO:
        if not _configured(provider):
            continue
        try:
            discovered.extend(await _discover(provider))
        except HTTPException:
            errors.append(provider)
    return {"models": discovered, "discovery": "live", "providers_queried": [p for p in PROVIDER_INFO if _configured(p)], "providers_with_errors": errors}

@app.post("/api/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    provider, separator, model = request.model.partition("/")
    if not separator or not model or provider not in PROVIDER_INFO:
        raise HTTPException(status_code=400, detail="Use a supported provider/model identifier.")
    body: dict[str, Any] = {"messages": [{"role": m.role, "content": m.content} for m in request.messages], "temperature": request.temperature, "max_tokens": request.max_tokens}

    if provider in {"openrouter", "openai", "ollama"}:
        if provider != "ollama" and not _key(provider):
            raise HTTPException(status_code=503, detail=f"Configure {provider.upper()} credentials on the server.")
        base = {"openrouter": "https://openrouter.ai/api/v1", "openai": "https://api.openai.com/v1", "ollama": os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")}[provider]
        result = await _post_openai_compatible(base, _key(provider), model, body)
    elif provider == "google":
        key = _key(provider)
        if not key:
            raise HTTPException(status_code=503, detail="Configure GOOGLE_API_KEY on the server.")
        system = "\n".join(m.content for m in request.messages if m.role == "system")
        contents = [{"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]} for m in request.messages if m.role != "system"]
        payload: dict[str, Any] = {"contents": contents, "generationConfig": {"temperature": request.temperature, "maxOutputTokens": request.max_tokens}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", params={"key": key}, json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"provider_error": response.text[:1200], "status": response.status_code})
        data = response.json()
        answer = "".join(part.get("text", "") for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []))
        result = {"id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion", "created": int(time.time()), "model": request.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}]}
    else:
        key = _key(provider)
        if not key:
            raise HTTPException(status_code=503, detail="Configure ANTHROPIC_API_KEY on the server.")
        system = "\n".join(m.content for m in request.messages if m.role == "system")
        payload = {"model": model, "max_tokens": request.max_tokens, "messages": [{"role": m.role, "content": m.content} for m in request.messages if m.role in {"user", "assistant"}]}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"provider_error": response.text[:1200], "status": response.status_code})
        data = response.json()
        answer = "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
        result = {"id": data.get("id", f"chatcmpl-{uuid.uuid4().hex}"), "object": "chat.completion", "created": int(time.time()), "model": request.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": data.get("stop_reason", "stop")}]}
    return result


# Persistent workspace resources (SQLite; replace with managed PostgreSQL before multi-instance production).
import json as _json
import sqlite3 as _sqlite3
from pathlib import Path as _Path
from fastapi import Body
from datetime import datetime, timezone

_DB_PATH = _Path(os.getenv("APOLO_DB_PATH", "/data/apolo-langdock.sqlite3"))
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _db():
    conn = _sqlite3.connect(_DB_PATH)
    conn.row_factory = _sqlite3.Row
    return conn

def _init_db():
    with _db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
          role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS agents (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          instructions TEXT NOT NULL DEFAULT '', model TEXT, tools TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflows (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          definition TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)
        conn.execute("PRAGMA foreign_keys=ON")

_init_db()

def _now():
    return datetime.now(timezone.utc).isoformat()

@app.get("/api/v1/conversations")
async def list_conversations():
    with _db() as conn:
        rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
    return {"conversations": [dict(row) for row in rows]}

@app.post("/api/v1/conversations")
async def create_conversation(payload: dict = Body(default={})):
    conversation_id = str(uuid.uuid4())
    now = _now()
    title = str(payload.get("title") or "Nova conversa")[:160]
    model = payload.get("model")
    with _db() as conn:
        conn.execute("INSERT INTO conversations(id,title,model,created_at,updated_at) VALUES(?,?,?,?,?)",
                     (conversation_id,title,model,now,now))
    return {"id":conversation_id,"title":title,"model":model,"created_at":now,"updated_at":now}

@app.get("/api/v1/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str):
    with _db() as conn:
        exists = conn.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not exists: raise HTTPException(status_code=404, detail="Conversation not found.")
        rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (conversation_id,)).fetchall()
    return {"messages":[dict(row) for row in rows]}

@app.post("/api/v1/conversations/{conversation_id}/messages")
async def add_message(conversation_id: str, payload: dict = Body(...)):
    role, content = payload.get("role"), payload.get("content")
    if role not in {"user","assistant","system"} or not isinstance(content,str) or not content.strip():
        raise HTTPException(status_code=422, detail="A valid role and non-empty content are required.")
    message_id, now = str(uuid.uuid4()), _now()
    with _db() as conn:
        exists = conn.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not exists: raise HTTPException(status_code=404, detail="Conversation not found.")
        conn.execute("INSERT INTO messages(id,conversation_id,role,content,created_at) VALUES(?,?,?,?,?)",
                     (message_id,conversation_id,role,content,now))
        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now,conversation_id))
    return {"id":message_id,"conversation_id":conversation_id,"role":role,"content":content,"created_at":now}

@app.delete("/api/v1/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    with _db() as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        result = conn.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
        if not result.rowcount: raise HTTPException(status_code=404, detail="Conversation not found.")
        conn.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    return {"deleted":True,"id":conversation_id}

@app.get("/api/v1/agents")
async def list_agents():
    with _db() as conn: rows=conn.execute("SELECT * FROM agents ORDER BY updated_at DESC").fetchall()
    return {"agents":[{**dict(row),"tools":_json.loads(row["tools"])} for row in rows]}

@app.post("/api/v1/agents")
async def save_agent(payload: dict = Body(...)):
    name=str(payload.get("name") or "").strip()
    if not name: raise HTTPException(status_code=422, detail="Agent name is required.")
    agent_id=str(payload.get("id") or uuid.uuid4()); now=_now()
    tools=payload.get("tools",[])
    if not isinstance(tools,list) or len(tools)>30: raise HTTPException(status_code=422, detail="tools must be a list with at most 30 entries.")
    with _db() as conn:
        conn.execute("""INSERT INTO agents(id,name,description,instructions,model,tools,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,
        instructions=excluded.instructions,model=excluded.model,tools=excluded.tools,updated_at=excluded.updated_at""",
        (agent_id,name,str(payload.get("description",""))[:1000],str(payload.get("instructions",""))[:12000],
         payload.get("model"),_json.dumps(tools),now,now))
    return {"id":agent_id,"name":name,"saved":True}

@app.get("/api/v1/workflows")
async def list_workflows():
    with _db() as conn: rows=conn.execute("SELECT * FROM workflows ORDER BY updated_at DESC").fetchall()
    return {"workflows":[{**dict(row),"definition":_json.loads(row["definition"])} for row in rows]}

@app.post("/api/v1/workflows")
async def save_workflow(payload: dict = Body(...)):
    name=str(payload.get("name") or "").strip()
    definition=payload.get("definition",{})
    if not name or not isinstance(definition,dict): raise HTTPException(status_code=422, detail="A workflow name and JSON definition are required.")
    if len(_json.dumps(definition))>100000: raise HTTPException(status_code=413, detail="Workflow definition is too large.")
    workflow_id=str(payload.get("id") or uuid.uuid4()); now=_now()
    with _db() as conn:
        conn.execute("""INSERT INTO workflows(id,name,description,definition,created_at,updated_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,
        definition=excluded.definition,updated_at=excluded.updated_at""",
        (workflow_id,name,str(payload.get("description",""))[:1000],_json.dumps(definition),now,now))
    return {"id":workflow_id,"name":name,"saved":True}
