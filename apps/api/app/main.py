from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

APP_VERSION = "0.3.0"
app = FastAPI(title="APOLO LangDock API", version=APP_VERSION, description="Open AI workspace API. Provider quotas and pricing are controlled by upstream providers.")
origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Authorization", "X-Workspace-ID", "X-API-Key"])

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
async def chat_completions(request: ChatRequest, http_request: Request):
    provider, separator, model = request.model.partition("/")
    if not separator or not model or provider not in PROVIDER_INFO:
        raise HTTPException(status_code=400, detail="Use a supported provider/model identifier.")
    body: dict[str, Any] = {"messages": [{"role": m.role, "content": m.content} for m in request.messages], "temperature": request.temperature, "max_tokens": request.max_tokens}
    _check_workspace_quota(http_request)
    usage_started = time.monotonic()

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
        usage_data = data.get("usageMetadata", {})
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
        usage_data = data.get("usage", {})
        answer = "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
        result = {"id": data.get("id", f"chatcmpl-{uuid.uuid4().hex}"), "object": "chat.completion", "created": int(time.time()), "model": request.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": data.get("stop_reason", "stop")}]}
    if provider in {"openrouter", "openai", "ollama"}:
        usage_data = result.get("usage", {}) if isinstance(result, dict) else {}
    _record_usage(http_request, request.model, provider, usage_data if isinstance(usage_data, dict) else {},
                  result, int((time.monotonic() - usage_started) * 1000), "succeeded")
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
          id TEXT PRIMARY KEY, workspace_id TEXT, title TEXT NOT NULL, model TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
          role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
          FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS agents (
          id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          instructions TEXT NOT NULL DEFAULT '', model TEXT, tools TEXT NOT NULL DEFAULT '[]',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflows (
          id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          definition TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)
        for table in ("conversations", "agents", "workflows"):
            columns = {row[1] for row in conn.execute("PRAGMA table_info(" + table + ")").fetchall()}
            if "workspace_id" not in columns:
                conn.execute("ALTER TABLE " + table + " ADD COLUMN workspace_id TEXT")
        conn.execute("PRAGMA foreign_keys=ON")

_init_db()

def _now():
    return datetime.now(timezone.utc).isoformat()

@app.get("/api/v1/conversations")
async def list_conversations(request: Request):
    workspace_id = request.state.workspace_id
    with _db() as conn:
        rows = conn.execute("SELECT * FROM conversations WHERE workspace_id=? ORDER BY updated_at DESC", (workspace_id,)).fetchall()
    return {"conversations": [dict(row) for row in rows]}

@app.post("/api/v1/conversations")
async def create_conversation(payload: dict = Body(default={}), request: Request = None):
    conversation_id = str(uuid.uuid4())
    now = _now()
    title = str(payload.get("title") or "Nova conversa")[:160]
    model = payload.get("model")
    with _db() as conn:
        conn.execute("INSERT INTO conversations(id,workspace_id,title,model,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     (conversation_id,request.state.workspace_id,title,model,now,now))
    return {"id":conversation_id,"title":title,"model":model,"created_at":now,"updated_at":now}

@app.get("/api/v1/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str, request: Request):
    with _db() as conn:
        exists = conn.execute("SELECT 1 FROM conversations WHERE id=? AND workspace_id=?", (conversation_id,request.state.workspace_id)).fetchone()
        if not exists: raise HTTPException(status_code=404, detail="Conversation not found.")
        rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at", (conversation_id,)).fetchall()
    return {"messages":[dict(row) for row in rows]}

@app.post("/api/v1/conversations/{conversation_id}/messages")
async def add_message(conversation_id: str, payload: dict = Body(...), request: Request = None):
    role, content = payload.get("role"), payload.get("content")
    if role not in {"user","assistant","system"} or not isinstance(content,str) or not content.strip():
        raise HTTPException(status_code=422, detail="A valid role and non-empty content are required.")
    message_id, now = str(uuid.uuid4()), _now()
    with _db() as conn:
        exists = conn.execute("SELECT 1 FROM conversations WHERE id=? AND workspace_id=?", (conversation_id,request.state.workspace_id)).fetchone()
        if not exists: raise HTTPException(status_code=404, detail="Conversation not found.")
        conn.execute("INSERT INTO messages(id,conversation_id,role,content,created_at) VALUES(?,?,?,?,?)",
                     (message_id,conversation_id,role,content,now))
        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now,conversation_id))
    return {"id":message_id,"conversation_id":conversation_id,"role":role,"content":content,"created_at":now}

@app.delete("/api/v1/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    with _db() as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        result = conn.execute("DELETE FROM conversations WHERE id=? AND workspace_id=?", (conversation_id,request.state.workspace_id))
        if not result.rowcount: raise HTTPException(status_code=404, detail="Conversation not found.")
        conn.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    return {"deleted":True,"id":conversation_id}

@app.get("/api/v1/agents")
async def list_agents(request: Request):
    with _db() as conn: rows=conn.execute("SELECT * FROM agents WHERE workspace_id=? ORDER BY updated_at DESC",(request.state.workspace_id,)).fetchall()
    return {"agents":[{**dict(row),"tools":_json.loads(row["tools"])} for row in rows]}

@app.post("/api/v1/agents")
async def save_agent(payload: dict = Body(...), request: Request = None):
    name=str(payload.get("name") or "").strip()
    if not name: raise HTTPException(status_code=422, detail="Agent name is required.")
    agent_id=str(payload.get("id") or uuid.uuid4()); now=_now()
    tools=payload.get("tools",[])
    if not isinstance(tools,list) or len(tools)>30: raise HTTPException(status_code=422, detail="tools must be a list with at most 30 entries.")
    with _db() as conn:
        existing=conn.execute("SELECT workspace_id FROM agents WHERE id=?",(agent_id,)).fetchone()
        if existing and existing["workspace_id"] != request.state.workspace_id:
            raise HTTPException(status_code=404,detail="Agent not found.")
        conn.execute("""INSERT INTO agents(id,workspace_id,name,description,instructions,model,tools,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,
        instructions=excluded.instructions,model=excluded.model,tools=excluded.tools,updated_at=excluded.updated_at
        WHERE agents.workspace_id=excluded.workspace_id""",
        (agent_id,request.state.workspace_id,name,str(payload.get("description",""))[:1000],str(payload.get("instructions",""))[:12000],
         payload.get("model"),_json.dumps(tools),now,now))
    return {"id":agent_id,"name":name,"saved":True}

@app.get("/api/v1/workflows")
async def list_workflows(request: Request):
    with _db() as conn: rows=conn.execute("SELECT * FROM workflows WHERE workspace_id=? ORDER BY updated_at DESC",(request.state.workspace_id,)).fetchall()
    return {"workflows":[{**dict(row),"definition":_json.loads(row["definition"])} for row in rows]}

@app.post("/api/v1/workflows")
async def save_workflow(payload: dict = Body(...), request: Request = None):
    name=str(payload.get("name") or "").strip()
    definition=payload.get("definition",{})
    if not name or not isinstance(definition,dict): raise HTTPException(status_code=422, detail="A workflow name and JSON definition are required.")
    if len(_json.dumps(definition))>100000: raise HTTPException(status_code=413, detail="Workflow definition is too large.")
    workflow_id=str(payload.get("id") or uuid.uuid4()); now=_now()
    with _db() as conn:
        existing=conn.execute("SELECT workspace_id FROM workflows WHERE id=?",(workflow_id,)).fetchone()
        if existing and existing["workspace_id"] != request.state.workspace_id:
            raise HTTPException(status_code=404,detail="Workflow not found.")
        conn.execute("""INSERT INTO workflows(id,workspace_id,name,description,definition,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,
        definition=excluded.definition,updated_at=excluded.updated_at WHERE workflows.workspace_id=excluded.workspace_id""",
        (workflow_id,request.state.workspace_id,name,str(payload.get("description",""))[:1000],_json.dumps(definition),now,now))
    return {"id":workflow_id,"name":name,"saved":True}


# Server-sent events (SSE). OpenAI-compatible adapters stream native deltas.
from fastapi.responses import StreamingResponse
import asyncio

async def _openai_stream(base_url: str, key: str | None, model: str, body: dict[str, Any]):
    headers={"Content-Type":"application/json"}
    if key: headers["Authorization"]=f"Bearer {key}"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST",f"{base_url.rstrip('/')}/chat/completions",
             headers=headers,json={**body,"model":model,"stream":True}) as response:
            if response.status_code >= 400:
                detail=(await response.aread()).decode("utf-8","replace")[:1000]
                yield "event: error\ndata: "+_json.dumps({"error":detail})+"\n\n"
                return
            async for line in response.aiter_lines():
                if not line.startswith("data:"): continue
                raw=line[5:].strip()
                if raw=="[DONE]":
                    yield "data: [DONE]\n\n"
                    return
                try:
                    packet=_json.loads(raw)
                    delta=packet.get("choices",[{}])[0].get("delta",{}).get("content")
                    if delta:
                        yield "data: "+_json.dumps({"delta":delta},ensure_ascii=False)+"\n\n"
                except (ValueError,TypeError,IndexError):
                    continue

async def _anthropic_stream(model: str, messages: list[ChatMessage], max_tokens: int, temperature: float):
    key=_key("anthropic")
    if not key:
        yield "event: error\ndata: "+_json.dumps({"error":"Configure ANTHROPIC_API_KEY."})+"\n\n"
        return
    system="\n".join(m.content for m in messages if m.role=="system")
    payload={"model":model,"max_tokens":max_tokens,"temperature":temperature,
             "messages":[{"role":m.role,"content":m.content} for m in messages if m.role in {"user","assistant"}],"stream":True}
    if system: payload["system"]=system
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST","https://api.anthropic.com/v1/messages",
             headers={"x-api-key":key,"anthropic-version":"2023-06-01","content-type":"application/json"},json=payload) as response:
            if response.status_code>=400:
                yield "event: error\ndata: "+_json.dumps({"error":(await response.aread()).decode("utf-8","replace")[:1000]})+"\n\n"
                return
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    try:
                        event=_json.loads(line[5:].strip())
                        if event.get("type")=="content_block_delta":
                            delta=event.get("delta",{}).get("text")
                            if delta: yield "data: "+_json.dumps({"delta":delta},ensure_ascii=False)+"\n\n"
                    except ValueError: pass
    yield "data: [DONE]\n\n"

async def _google_stream(model: str, messages: list[ChatMessage], max_tokens: int, temperature: float):
    key=_key("google")
    if not key:
        yield "event: error\ndata: "+_json.dumps({"error":"Configure GOOGLE_API_KEY."})+"\n\n"
        return
    system="\n".join(m.content for m in messages if m.role=="system")
    contents=[{"role":"model" if m.role=="assistant" else "user","parts":[{"text":m.content}]} for m in messages if m.role!="system"]
    payload={"contents":contents,"generationConfig":{"temperature":temperature,"maxOutputTokens":max_tokens}}
    if system: payload["systemInstruction"]={"parts":[{"text":system}]}
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST",url,params={"key":key,"alt":"sse"},json=payload) as response:
            if response.status_code>=400:
                yield "event: error\ndata: "+_json.dumps({"error":(await response.aread()).decode("utf-8","replace")[:1000]})+"\n\n"
                return
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    try:
                        packet=_json.loads(line[5:].strip())
                        for part in packet.get("candidates",[{}])[0].get("content",{}).get("parts",[]):
                            delta=part.get("text")
                            if delta: yield "data: "+_json.dumps({"delta":delta},ensure_ascii=False)+"\n\n"
                    except (ValueError,IndexError,TypeError): pass
    yield "data: [DONE]\n\n"

@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    provider, separator, model=request.model.partition("/")
    if not separator or not model or provider not in PROVIDER_INFO:
        raise HTTPException(status_code=400,detail="Use a supported provider/model identifier.")
    body={"messages":[{"role":m.role,"content":m.content} for m in request.messages],
          "temperature":request.temperature,"max_tokens":request.max_tokens}
    if provider in {"openrouter","openai","ollama"}:
        if provider!="ollama" and not _key(provider):
            raise HTTPException(status_code=503,detail=f"Configure {provider.upper()} credentials on the server.")
        base={"openrouter":"https://openrouter.ai/api/v1","openai":"https://api.openai.com/v1",
              "ollama":os.getenv("OLLAMA_BASE_URL","http://host.docker.internal:11434/v1")}[provider]
        generator=_openai_stream(base,_key(provider),model,body)
    elif provider=="anthropic":
        generator=_anthropic_stream(model,request.messages,request.max_tokens or 1024,request.temperature or 0.7)
    else:
        generator=_google_stream(model,request.messages,request.max_tokens or 1024,request.temperature or 0.7)
    return StreamingResponse(generator,media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no","Connection":"keep-alive"})


# Identity and workspace foundation. Tokens are opaque, stored only as SHA-256 hashes.
import hashlib as _hashlib
import secrets as _secrets
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer=HTTPBearer(auto_error=False)
def _password_hash(password:str, salt:bytes|None=None)->str:
    salt=salt or _secrets.token_bytes(16)
    digest=_hashlib.pbkdf2_hmac("sha256",password.encode(),salt,310000)
    return salt.hex()+":"+digest.hex()

def _verify_password(password:str, encoded:str)->bool:
    try:
        salt_hex,digest_hex=encoded.split(":",1)
        return _secrets.compare_digest(_password_hash(password,bytes.fromhex(salt_hex)).split(":",1)[1],digest_hex)
    except (ValueError,TypeError): return False

def _token_hash(token:str)->str:
    return _hashlib.sha256(token.encode()).hexdigest()

def _current_user(credentials:HTTPAuthorizationCredentials|None=Depends(_bearer)):
    if not credentials: raise HTTPException(status_code=401,detail="Authentication required.")
    with _db() as conn:
        row=conn.execute("""SELECT u.id,u.email,u.created_at FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>?""",(_token_hash(credentials.credentials),_now())).fetchone()
    if not row: raise HTTPException(status_code=401,detail="Session invalid or expired.")
    return dict(row)

with _db() as conn:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,token_hash TEXT UNIQUE NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS workspace_members(workspace_id TEXT NOT NULL,user_id TEXT NOT NULL,role TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(workspace_id,user_id));
    """)

@app.post("/api/v1/auth/register")
async def register(payload:dict=Body(...)):
    email=str(payload.get("email") or "").strip().lower()
    password=payload.get("password")
    if "@" not in email or len(email)>254: raise HTTPException(status_code=422,detail="A valid email is required.")
    if not isinstance(password,str) or len(password)<12: raise HTTPException(status_code=422,detail="Password must contain at least 12 characters.")
    user_id=str(uuid.uuid4()); now=_now()
    try:
        with _db() as conn:
            conn.execute("INSERT INTO users(id,email,password_hash,created_at) VALUES(?,?,?,?)",(user_id,email,_password_hash(password),now))
    except _sqlite3.IntegrityError: raise HTTPException(status_code=409,detail="Email already registered.")
    token=_secrets.token_urlsafe(36); expires=(datetime.now(timezone.utc)+__import__("datetime").timedelta(days=7)).isoformat()
    with _db() as conn: conn.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)",(str(uuid.uuid4()),user_id,_token_hash(token),expires,now))
    return {"access_token":token,"token_type":"bearer","expires_at":expires,"user":{"id":user_id,"email":email}}

@app.post("/api/v1/auth/login")
async def login(payload:dict=Body(...)):
    email=str(payload.get("email") or "").strip().lower(); password=payload.get("password")
    with _db() as conn: user=conn.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not user or not isinstance(password,str) or not _verify_password(password,user["password_hash"]):
        raise HTTPException(status_code=401,detail="Invalid email or password.")
    token=_secrets.token_urlsafe(36); now=_now()
    expires=(datetime.now(timezone.utc)+__import__("datetime").timedelta(days=7)).isoformat()
    with _db() as conn: conn.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)",(str(uuid.uuid4()),user["id"],_token_hash(token),expires,now))
    return {"access_token":token,"token_type":"bearer","expires_at":expires}

@app.get("/api/v1/auth/me")
async def auth_me(user:dict=Depends(_current_user)):
    return {"user":user}

@app.post("/api/v1/workspaces")
async def create_workspace(payload:dict=Body(...),user:dict=Depends(_current_user)):
    name=str(payload.get("name") or "").strip()
    if not name or len(name)>120: raise HTTPException(status_code=422,detail="Workspace name is required (max 120 characters).")
    workspace_id=str(uuid.uuid4()); now=_now()
    with _db() as conn:
        conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)",(workspace_id,name,now))
        conn.execute("INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(?,?,?,?)",(workspace_id,user["id"],"owner",now))
    return {"id":workspace_id,"name":name,"role":"owner","created_at":now}

@app.get("/api/v1/workspaces")
async def list_workspaces(user:dict=Depends(_current_user)):
    with _db() as conn:
        rows=conn.execute("""SELECT w.id,w.name,w.created_at,m.role FROM workspaces w
        JOIN workspace_members m ON m.workspace_id=w.id WHERE m.user_id=? ORDER BY w.created_at""",(user["id"],)).fetchall()
    return {"workspaces":[dict(row) for row in rows]}


# Private API guard: bearer identity plus explicit workspace membership.
from fastapi.responses import JSONResponse

@app.middleware("http")
async def enforce_identity_and_workspace(request: Request, call_next):
    path = request.url.path
    public = path in {"/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/providers", "/api/v1/models", "/api/v1/public/models", "/api/v1/public/chat/completions"}
    if path.startswith("/api/v1/") and not public and request.method != "OPTIONS":
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "Authentication required."})
        token = auth.split(" ", 1)[1].strip()
        with _db() as conn:
            row = conn.execute("""SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>?""", (_token_hash(token), _now())).fetchone()
        if not row:
            return JSONResponse(status_code=401, content={"detail": "Session invalid or expired."})
        request.state.user_id = row["id"]
        scoped = (path.startswith("/api/v1/conversations") or path.startswith("/api/v1/agents")
                  or path.startswith("/api/v1/workflows") or path.startswith("/api/v1/workflow-runs") or path.startswith("/api/v1/agent-runs") or path.startswith("/api/v1/chat/") or path.startswith("/api/v1/mcp/") or path.startswith("/api/v1/api-keys") or path.startswith("/api/v1/audit-logs") or path.startswith("/api/v1/usage/") or path.startswith("/api/v1/workspace/"))
        if scoped:
            workspace_id = request.headers.get("x-workspace-id", "").strip()
            if not workspace_id:
                return JSONResponse(status_code=400, content={"detail": "X-Workspace-ID header is required."})
            with _db() as conn:
                member = conn.execute("SELECT 1 FROM workspace_members WHERE workspace_id=? AND user_id=?",
                                      (workspace_id, row["id"])).fetchone()
            if not member:
                return JSONResponse(status_code=403, content={"detail": "Workspace access denied."})
            request.state.workspace_id = workspace_id
    return await call_next(request)


@app.post("/api/v1/auth/logout")
async def logout(user: dict = Depends(_current_user), credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    if credentials:
        with _db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(credentials.credentials),))
    return {"logged_out": True}


# Bounded agent execution. Tool metadata is never executed by this runtime.
with _db() as conn:
    conn.execute("""CREATE TABLE IF NOT EXISTS agent_runs(
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, agent_ids TEXT NOT NULL,
        prompt TEXT NOT NULL, status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
        trace TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
    )""")

@app.post("/api/v1/agents/{agent_id}/run")
async def run_agent(agent_id: str, payload: dict = Body(...), request: Request = None):
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        raise HTTPException(status_code=422, detail="A prompt of 1-20000 characters is required.")
    with _db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id=? AND workspace_id=?",
                             (agent_id, request.state.workspace_id)).fetchone()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    if _json.loads(agent["tools"]):
        raise HTTPException(status_code=409, detail="This agent declares tools, but tool execution is disabled until explicit allowlists and approval gates are configured.")
    if not agent["model"]:
        raise HTTPException(status_code=422, detail="Choose a model for this agent before running it.")
    run_id, created = str(uuid.uuid4()), _now()
    trace = [{"step": 1, "agent_id": agent_id, "model": agent["model"], "status": "running"}]
    try:
        response = await chat_completions(ChatRequest(model=agent["model"], messages=[
            ChatMessage(role="system", content=agent["instructions"] or "You are a helpful assistant."),
            ChatMessage(role="user", content=prompt)
        ]), request)
        output = response["choices"][0]["message"]["content"]
        trace[0]["status"] = "completed"
        with _db() as conn:
            conn.execute("INSERT INTO agent_runs(id,workspace_id,agent_ids,prompt,status,output,trace,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (run_id, request.state.workspace_id, _json.dumps([agent_id]), prompt, "completed", output, _json.dumps(trace), created))
        return {"run_id": run_id, "status": "completed", "output": output, "trace": trace}
    except Exception as exc:
        trace[0]["status"] = "failed"
        with _db() as conn:
            conn.execute("INSERT INTO agent_runs(id,workspace_id,agent_ids,prompt,status,output,trace,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (run_id, request.state.workspace_id, _json.dumps([agent_id]), prompt, "failed", "", _json.dumps(trace), created))
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail="Agent execution failed.") from exc


@app.post("/api/v1/agents/orchestrate")
async def orchestrate_agents(payload: dict = Body(...), request: Request = None):
    agent_ids = payload.get("agent_ids")
    prompt = payload.get("prompt")
    max_steps = payload.get("max_steps", 3)
    if not isinstance(agent_ids, list) or not 1 <= len(agent_ids) <= 5 or len(set(agent_ids)) != len(agent_ids):
        raise HTTPException(status_code=422, detail="agent_ids must contain 1-5 unique agent IDs.")
    if not isinstance(max_steps, int) or not 1 <= max_steps <= 5:
        raise HTTPException(status_code=422, detail="max_steps must be between 1 and 5.")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
        raise HTTPException(status_code=422, detail="A prompt of 1-20000 characters is required.")
    with _db() as conn:
        placeholders = ",".join("?" for _ in agent_ids)
        rows = conn.execute("SELECT * FROM agents WHERE workspace_id=? AND id IN (" + placeholders + ")",
                            [request.state.workspace_id, *agent_ids]).fetchall()
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(agent_ids):
        raise HTTPException(status_code=404, detail="One or more agents were not found in this workspace.")
    selected = [by_id[item] for item in agent_ids[:max_steps]]
    if any(_json.loads(row["tools"]) for row in selected):
        raise HTTPException(status_code=409, detail="Orchestration with declared tools is disabled until explicit allowlists and approval gates are configured.")
    if any(not row["model"] for row in selected):
        raise HTTPException(status_code=422, detail="Every selected agent must have a model.")
    run_id, created = str(uuid.uuid4()), _now()
    trace, previous = [], ""
    try:
        for index, agent in enumerate(selected, start=1):
            step_prompt = prompt if index == 1 else (
                "Original task:\n" + prompt + "\n\nPrevious agent result:\n" + previous +
                "\n\nContinue the task. Check the prior result and provide the next useful contribution."
            )
            trace.append({"step": index, "agent_id": agent["id"], "model": agent["model"], "status": "running"})
            response = await chat_completions(ChatRequest(model=agent["model"], messages=[
                ChatMessage(role="system", content=agent["instructions"] or "You are a helpful assistant."),
                ChatMessage(role="user", content=step_prompt)
            ]), request)
            previous = response["choices"][0]["message"]["content"]
            trace[-1]["status"] = "completed"
        with _db() as conn:
            conn.execute("INSERT INTO agent_runs(id,workspace_id,agent_ids,prompt,status,output,trace,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (run_id, request.state.workspace_id, _json.dumps([row["id"] for row in selected]), prompt, "completed", previous, _json.dumps(trace), created))
        return {"run_id": run_id, "status": "completed", "output": previous, "trace": trace}
    except Exception as exc:
        if trace:
            trace[-1]["status"] = "failed"
        with _db() as conn:
            conn.execute("INSERT INTO agent_runs(id,workspace_id,agent_ids,prompt,status,output,trace,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (run_id, request.state.workspace_id, _json.dumps([row["id"] for row in selected]), prompt, "failed", previous, _json.dumps(trace), created))
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail="Agent orchestration failed.") from exc


@app.get("/api/v1/agent-runs")
async def list_agent_runs(request: Request):
    with _db() as conn:
        rows = conn.execute("SELECT * FROM agent_runs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50",
                            (request.state.workspace_id,)).fetchall()
    return {"runs": [{**dict(row), "agent_ids": _json.loads(row["agent_ids"]), "trace": _json.loads(row["trace"])} for row in rows]}


with _db() as conn:
    conn.execute("""CREATE TABLE IF NOT EXISTS workflow_runs(
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, workflow_id TEXT NOT NULL,
        status TEXT NOT NULL, input TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
        trace TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
    )""")

@app.post("/api/v1/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, payload: dict = Body(...), request: Request = None):
    user_input = payload.get("input")
    if not isinstance(user_input, str) or not user_input.strip() or len(user_input) > 20000:
        raise HTTPException(status_code=422, detail="A workflow input of 1-20000 characters is required.")
    with _db() as conn:
        workflow = conn.execute("SELECT * FROM workflows WHERE id=? AND workspace_id=?",
                                (workflow_id, request.state.workspace_id)).fetchone()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    definition = _json.loads(workflow["definition"])
    nodes, edges = definition.get("nodes"), definition.get("edges")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 20 or not isinstance(edges, list) or len(edges) > 30:
        raise HTTPException(status_code=422, detail="Workflow must contain 1-20 nodes and at most 30 edges.")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or node["id"] in by_id:
            raise HTTPException(status_code=422, detail="Every node needs a unique string ID.")
        if node.get("type") not in {"input", "prompt", "model", "output"}:
            raise HTTPException(status_code=422, detail="Unsupported workflow node type.")
        by_id[node["id"]] = node
    incoming = {node_id: [] for node_id in by_id}
    outgoing = {node_id: [] for node_id in by_id}
    for edge in edges:
        if not isinstance(edge, dict):
            raise HTTPException(status_code=422, detail="Invalid workflow edge.")
        source, target = edge.get("source"), edge.get("target")
        if source not in by_id or target not in by_id or source == target:
            raise HTTPException(status_code=422, detail="Workflow edges must reference distinct existing nodes.")
        outgoing[source].append(target)
        incoming[target].append(source)
    ready = [node_id for node_id in by_id if not incoming[node_id]]
    order = []
    remaining = {key: list(value) for key, value in incoming.items()}
    while ready:
        current = ready.pop(0)
        order.append(current)
        for target in outgoing[current]:
            remaining[target].remove(current)
            if not remaining[target]:
                ready.append(target)
    if len(order) != len(by_id):
        raise HTTPException(status_code=422, detail="Workflow contains a cycle.")
    input_nodes = [node for node in nodes if node["type"] == "input"]
    if len(input_nodes) != 1:
        raise HTTPException(status_code=422, detail="A workflow must have exactly one input node.")
    values, trace = {}, []
    run_id, created = str(uuid.uuid4()), _now()
    try:
        for node_id in order:
            node = by_id[node_id]
            config = node.get("config") if isinstance(node.get("config"), dict) else {}
            previous = "\n\n".join(values[item] for item in incoming[node_id] if item in values)
            node_type = node["type"]
            if node_type == "input":
                value = user_input
            elif node_type == "prompt":
                instruction = str(config.get("instructions") or "")[:12000]
                value = (instruction + "\n\n" + previous).strip()
            elif node_type == "model":
                selected_model = config.get("model")
                if not isinstance(selected_model, str) or "/" not in selected_model:
                    raise HTTPException(status_code=422, detail="Every model node needs a provider/model ID.")
                system_prompt = str(config.get("system") or "Follow the workflow instructions and produce the requested result.")[:12000]
                result = await chat_completions(ChatRequest(model=selected_model, messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=previous or user_input)
                ]), request)
                value = result["choices"][0]["message"]["content"]
            else:
                value = previous or user_input
            values[node_id] = value
            trace.append({"node_id": node_id, "type": node_type, "status": "completed"})
        output_nodes = [node["id"] for node in nodes if node["type"] == "output"]
        output = "\n\n".join(values[item] for item in output_nodes) if output_nodes else values[order[-1]]
        with _db() as conn:
            conn.execute("INSERT INTO workflow_runs(id,workspace_id,workflow_id,status,input,output,trace,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (run_id, request.state.workspace_id, workflow_id, "completed", user_input, output, _json.dumps(trace), created))
        return {"run_id": run_id, "status": "completed", "output": output, "trace": trace}
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=502, detail="Workflow execution failed.") from exc


@app.get("/api/v1/workflow-runs")
async def list_workflow_runs(request: Request):
    with _db() as conn:
        rows = conn.execute("SELECT * FROM workflow_runs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 50",
                            (request.state.workspace_id,)).fetchall()
    return {"runs": [dict(row, trace=_json.loads(row["trace"])) for row in rows]}


# MCP registry and approval-gated client. Remote hosts and stdio processes are
# administrator-allowlisted; discovered tools are denied until a workspace owner approves them.
from .mcp_runtime import MCPRuntimeError, discover_tools as _mcp_discover_tools, invoke_tool as _mcp_invoke_tool, stdio_config as _mcp_stdio_config, validate_http_endpoint as _mcp_validate_endpoint

with _db() as conn:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS mcp_servers(
      id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
      transport TEXT NOT NULL, endpoint TEXT, config_key TEXT, auth_ciphertext TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS mcp_tools(
      workspace_id TEXT NOT NULL, server_id TEXT NOT NULL, name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '', input_schema TEXT NOT NULL DEFAULT '{}',
      approved INTEGER NOT NULL DEFAULT 0, discovered_at TEXT NOT NULL,
      PRIMARY KEY(workspace_id,server_id,name),
      FOREIGN KEY(server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE
    );
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(mcp_servers)").fetchall()}
    if "auth_ciphertext" not in columns:
        conn.execute("ALTER TABLE mcp_servers ADD COLUMN auth_ciphertext TEXT")


@app.get("/api/v1/mcp/servers")
async def list_mcp_servers(request: Request):
    with _db() as conn:
        rows = conn.execute("SELECT * FROM mcp_servers WHERE workspace_id=? ORDER BY created_at DESC",
                            (request.state.workspace_id,)).fetchall()
    return {"servers": [{**{key: row[key] for key in ("id","workspace_id","name","transport","endpoint","config_key","created_at","updated_at")}, "credential_configured": bool(row["auth_ciphertext"])} for row in rows]}


@app.post("/api/v1/mcp/servers")
async def register_mcp_server(payload: dict = Body(...), request: Request = None):
    _require_workspace_role(request, {'owner', 'admin'})
    name = str(payload.get("name") or "").strip()
    transport = payload.get("transport")
    if not name or len(name) > 100:
        raise HTTPException(status_code=422, detail="A server name (max 100 characters) is required.")
    endpoint, config_key, auth_ciphertext = None, None, None
    bearer_token = payload.get("bearer_token")
    if bearer_token is not None and (not isinstance(bearer_token, str) or not bearer_token.strip() or len(bearer_token) > 4096):
        raise HTTPException(status_code=422, detail="bearer_token must be a non-empty string up to 4096 characters.")
    try:
        if transport == "streamable-http":
            endpoint = _mcp_validate_endpoint(str(payload.get("endpoint") or ""))
            if bearer_token:
                auth_ciphertext = _mcp_encrypt_secret(bearer_token.strip())
        elif transport == "stdio":
            if bearer_token:
                raise MCPRuntimeError("Bearer credentials are supported only for Streamable HTTP servers.")
            config_key = str(payload.get("config_key") or "")
            if not config_key or len(config_key) > 80:
                raise MCPRuntimeError("A valid administrator-configured stdio alias is required.")
            _mcp_stdio_config(config_key)
        else:
            raise MCPRuntimeError("Transport must be streamable-http or stdio.")
    except MCPRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    server_id, now = str(uuid.uuid4()), _now()
    with _db() as conn:
        conn.execute("INSERT INTO mcp_servers(id,workspace_id,name,transport,endpoint,config_key,auth_ciphertext,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (server_id, request.state.workspace_id, name, transport, endpoint, config_key, auth_ciphertext, now, now))
    _audit(request.state.workspace_id, request.state.user_id, "mcp.server.created", "mcp_server", server_id, {"transport": transport, "name": name})
    return {"id": server_id, "name": name, "transport": transport, "created_at": now}


@app.delete("/api/v1/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str, request: Request):
    _require_workspace_role(request, {'owner', 'admin'})
    with _db() as conn:
        conn.execute("DELETE FROM mcp_tools WHERE workspace_id=? AND server_id=?",
                     (request.state.workspace_id, server_id))
        result = conn.execute("DELETE FROM mcp_servers WHERE id=? AND workspace_id=?",
                              (server_id, request.state.workspace_id))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    _audit(request.state.workspace_id, request.state.user_id, "mcp.server.deleted", "mcp_server", server_id)
    return {"deleted": True, "id": server_id}


@app.post("/api/v1/mcp/servers/{server_id}/discover")
async def discover_mcp_server_tools(server_id: str, request: Request):
    with _db() as conn:
        server = conn.execute("SELECT * FROM mcp_servers WHERE id=? AND workspace_id=?",
                              (server_id, request.state.workspace_id)).fetchone()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    try:
        found = await asyncio.wait_for(
            _mcp_discover_tools(server["transport"], server["endpoint"], server["config_key"], _mcp_decrypt_secret(server["auth_ciphertext"])), timeout=25
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP discovery failed: {str(exc)[:300]}") from exc
    now = _now()
    with _db() as conn:
        for item in found[:100]:
            tool_name = item.get("name")
            if not isinstance(tool_name, str) or not tool_name or len(tool_name) > 128:
                continue
            schema = item.get("input_schema") if isinstance(item.get("input_schema"), dict) else {}
            conn.execute("""INSERT INTO mcp_tools(workspace_id,server_id,name,description,input_schema,approved,discovered_at)
                VALUES(?,?,?,?,?,0,?) ON CONFLICT(workspace_id,server_id,name) DO UPDATE SET
                description=excluded.description,input_schema=excluded.input_schema,discovered_at=excluded.discovered_at""",
                (request.state.workspace_id, server_id, tool_name, str(item.get("description") or "")[:2000],
                 _json.dumps(schema)[:30000], now))
        rows = conn.execute("SELECT * FROM mcp_tools WHERE workspace_id=? AND server_id=? ORDER BY name",
                            (request.state.workspace_id, server_id)).fetchall()
    return {"server_id": server_id, "discovered": len(found), "tools": [
        {**dict(row), "input_schema": _json.loads(row["input_schema"]), "approved": bool(row["approved"])}
        for row in rows
    ]}


@app.get("/api/v1/mcp/servers/{server_id}/tools")
async def list_mcp_tools(server_id: str, request: Request):
    with _db() as conn:
        exists = conn.execute("SELECT 1 FROM mcp_servers WHERE id=? AND workspace_id=?",
                              (server_id, request.state.workspace_id)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="MCP server not found.")
        rows = conn.execute("SELECT * FROM mcp_tools WHERE workspace_id=? AND server_id=? ORDER BY name",
                            (request.state.workspace_id, server_id)).fetchall()
    return {"tools": [{**dict(row), "input_schema": _json.loads(row["input_schema"]),
                       "approved": bool(row["approved"])} for row in rows]}


@app.post("/api/v1/mcp/servers/{server_id}/tools/{tool_name}/approval")
async def set_mcp_tool_approval(server_id: str, tool_name: str, payload: dict = Body(...), request: Request = None):
    _require_workspace_role(request, {'owner', 'admin'})
    approved = payload.get("approved")
    if not isinstance(approved, bool):
        raise HTTPException(status_code=422, detail="approved must be a boolean.")
    with _db() as conn:
        result = conn.execute("UPDATE mcp_tools SET approved=? WHERE workspace_id=? AND server_id=? AND name=?",
                              (1 if approved else 0, request.state.workspace_id, server_id, tool_name))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Discovered MCP tool not found.")
    _audit(request.state.workspace_id, request.state.user_id, "mcp.tool.approval_changed", "mcp_tool", tool_name, {"server_id": server_id, "approved": approved})
    return {"server_id": server_id, "tool_name": tool_name, "approved": approved}


@app.post("/api/v1/mcp/servers/{server_id}/tools/{tool_name}/call")
async def call_approved_mcp_tool(server_id: str, tool_name: str, payload: dict = Body(default={}), request: Request = None):
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict) or len(_json.dumps(arguments)) > 30000:
        raise HTTPException(status_code=422, detail="Tool arguments must be a JSON object no larger than 30 KB.")
    with _db() as conn:
        row = conn.execute("""SELECT s.*,t.approved FROM mcp_servers s JOIN mcp_tools t
            ON t.server_id=s.id AND t.workspace_id=s.workspace_id
            WHERE s.id=? AND s.workspace_id=? AND t.name=?""",
            (server_id, request.state.workspace_id, tool_name)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="MCP tool not found.")
    if not row["approved"]:
        raise HTTPException(status_code=403, detail="This MCP tool has not been approved by the workspace.")
    try:
        result = await asyncio.wait_for(
            _mcp_invoke_tool(row["transport"], tool_name, arguments, row["endpoint"], row["config_key"], _mcp_decrypt_secret(row["auth_ciphertext"])),
            timeout=30
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="MCP tool execution timed out.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP tool execution failed: {str(exc)[:300]}") from exc
    _audit(request.state.workspace_id, request.state.user_id, "mcp.tool.called", "mcp_tool", tool_name, {"server_id": server_id, "is_error": bool(result.get("is_error"))})
    return result


# MCP bearer credentials are encrypted at rest; configure a private Fernet key outside source control.
from cryptography.fernet import Fernet, InvalidToken

def _mcp_fernet() -> Fernet:
    key = os.getenv("APOLO_MCP_ENCRYPTION_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Configure APOLO_MCP_ENCRYPTION_KEY before storing MCP credentials.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(status_code=500, detail="APOLO_MCP_ENCRYPTION_KEY is invalid.") from exc

def _mcp_encrypt_secret(secret: str) -> str:
    return _mcp_fernet().encrypt(secret.encode("utf-8")).decode("ascii")

def _mcp_decrypt_secret(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return _mcp_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored MCP credential cannot be decrypted; verify the encryption key.") from exc


@app.post("/api/v1/mcp/servers/{server_id}/credentials")
async def set_mcp_server_credentials(server_id: str, payload: dict = Body(...), request: Request = None):
    _require_workspace_role(request, {'owner', 'admin'})
    token = payload.get("bearer_token")
    if not isinstance(token, str) or not token.strip() or len(token) > 4096:
        raise HTTPException(status_code=422, detail="A bearer_token up to 4096 characters is required.")
    with _db() as conn:
        server = conn.execute("SELECT transport FROM mcp_servers WHERE id=? AND workspace_id=?",
                              (server_id, request.state.workspace_id)).fetchone()
        if not server:
            raise HTTPException(status_code=404, detail="MCP server not found.")
        if server["transport"] != "streamable-http":
            raise HTTPException(status_code=400, detail="Bearer credentials are supported only for Streamable HTTP.")
        encrypted = _mcp_encrypt_secret(token.strip())
        conn.execute("UPDATE mcp_servers SET auth_ciphertext=?,updated_at=? WHERE id=? AND workspace_id=?",
                     (encrypted, _now(), server_id, request.state.workspace_id))
    _audit(request.state.workspace_id, request.state.user_id, "mcp.credentials.updated", "mcp_server", server_id)
    return {"server_id": server_id, "credential_configured": True}


@app.delete("/api/v1/mcp/servers/{server_id}/credentials")
async def delete_mcp_server_credentials(server_id: str, request: Request):
    _require_workspace_role(request, {'owner', 'admin'})
    with _db() as conn:
        result = conn.execute("UPDATE mcp_servers SET auth_ciphertext=NULL,updated_at=? WHERE id=? AND workspace_id=?",
                              (_now(), server_id, request.state.workspace_id))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    _audit(request.state.workspace_id, request.state.user_id, "mcp.credentials.revoked", "mcp_server", server_id)
    return {"server_id": server_id, "credential_configured": False}


# Workspace API keys, usage throttling, and audit trail.
with _db() as conn:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS api_keys(
      id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
      key_hash TEXT UNIQUE NOT NULL, key_prefix TEXT NOT NULL, scopes TEXT NOT NULL,
      expires_at TEXT, revoked_at TEXT, created_at TEXT NOT NULL, last_used_at TEXT
    );
    CREATE TABLE IF NOT EXISTS api_key_requests(
      id TEXT PRIMARY KEY, key_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
      route TEXT NOT NULL, model TEXT, created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_api_key_requests_window ON api_key_requests(key_id,created_at);
    CREATE TABLE IF NOT EXISTS audit_logs(
      id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, actor_user_id TEXT,
      action TEXT NOT NULL, resource_type TEXT NOT NULL, resource_id TEXT,
      details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_logs_workspace ON audit_logs(workspace_id,created_at);
    CREATE TABLE IF NOT EXISTS usage_events(
      id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, api_key_id TEXT, provider TEXT NOT NULL,
      model TEXT NOT NULL, prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER,
      cost_usd REAL, latency_ms INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_usage_workspace_created ON usage_events(workspace_id,created_at);
    CREATE TABLE IF NOT EXISTS workspace_usage_limits(
      workspace_id TEXT PRIMARY KEY, monthly_token_limit INTEGER, monthly_request_limit INTEGER,
      updated_at TEXT NOT NULL
    );
    """)


def _audit(workspace_id: str, actor_user_id: str | None, action: str,
           resource_type: str, resource_id: str | None = None, details: dict | None = None):
    with _db() as conn:
        conn.execute("INSERT INTO audit_logs(id,workspace_id,actor_user_id,action,resource_type,resource_id,details,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (str(uuid.uuid4()), workspace_id, actor_user_id, action, resource_type,
                      resource_id, _json.dumps(details or {})[:4000], _now()))


@app.post("/api/v1/api-keys")
async def create_api_key(payload: dict = Body(default={}), request: Request = None):
    _require_workspace_role(request, {'owner', 'admin'})
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=422, detail="API key name is required (max 100 characters).")
    scopes = payload.get("scopes", ["chat:completions", "models:read"])
    allowed_scopes = {"chat:completions", "models:read"}
    if (not isinstance(scopes, list) or not scopes or len(scopes) > 2
            or not all(isinstance(scope, str) for scope in scopes)
            or len(set(scopes)) != len(scopes) or any(scope not in allowed_scopes for scope in scopes)):
        raise HTTPException(status_code=422, detail="Scopes must be selected from chat:completions and models:read.")
    expires_in_days = payload.get("expires_in_days", 90)
    if isinstance(expires_in_days, bool) or not isinstance(expires_in_days, int) or not 1 <= expires_in_days <= 365:
        raise HTTPException(status_code=422, detail="expires_in_days must be between 1 and 365.")
    raw = "apolo_sk_" + _secrets.token_urlsafe(32)
    key_id, now = str(uuid.uuid4()), _now()
    expires = (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=expires_in_days)).isoformat()
    with _db() as conn:
        conn.execute("INSERT INTO api_keys(id,workspace_id,name,key_hash,key_prefix,scopes,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (key_id, request.state.workspace_id, name, _token_hash(raw), raw[:16],
                      _json.dumps(scopes), expires, now))
    _audit(request.state.workspace_id, request.state.user_id, "api_key.created", "api_key", key_id, {"name": name, "scopes": scopes, "expires_at": expires})
    return {"id": key_id, "name": name, "api_key": raw, "key_prefix": raw[:16],
            "scopes": scopes, "expires_at": expires, "warning": "Copy this key now. It cannot be displayed again."}


@app.get("/api/v1/api-keys")
async def list_api_keys(request: Request):
    with _db() as conn:
        rows = conn.execute("SELECT id,name,key_prefix,scopes,expires_at,revoked_at,created_at,last_used_at FROM api_keys WHERE workspace_id=? ORDER BY created_at DESC",
                            (request.state.workspace_id,)).fetchall()
    return {"api_keys": [{**dict(row), "scopes": _json.loads(row["scopes"])} for row in rows]}


@app.delete("/api/v1/api-keys/{key_id}")
async def revoke_api_key(key_id: str, request: Request):
    _require_workspace_role(request, {'owner', 'admin'})
    now = _now()
    with _db() as conn:
        result = conn.execute("UPDATE api_keys SET revoked_at=? WHERE id=? AND workspace_id=? AND revoked_at IS NULL",
                              (now, key_id, request.state.workspace_id))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Active API key not found.")
    _audit(request.state.workspace_id, request.state.user_id, "api_key.revoked", "api_key", key_id)
    return {"revoked": True, "id": key_id}


def _authenticate_api_key(request: Request, required_scope: str) -> dict:
    raw = request.headers.get("x-api-key", "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="X-API-Key is required.")
    now = _now()
    with _db() as conn:
        row = conn.execute("SELECT * FROM api_keys WHERE key_hash=? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)",
                           (_token_hash(raw), now)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="API key is invalid, revoked, or expired.")
    scopes = _json.loads(row["scopes"])
    if required_scope not in scopes:
        raise HTTPException(status_code=403, detail="API key does not include the required scope.")
    try:
        rpm = int(os.getenv("APOLO_API_KEY_RPM", "60"))
    except ValueError:
        rpm = 60
    rpm = min(max(rpm, 1), 600)
    cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(minutes=1)).isoformat()
    with _db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        retention_cutoff = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=2)).isoformat()
        conn.execute("DELETE FROM api_key_requests WHERE created_at<?", (retention_cutoff,))
        count = conn.execute("SELECT COUNT(*) FROM api_key_requests WHERE key_id=? AND created_at>=?",
                             (row["id"], cutoff)).fetchone()[0]
        if count >= rpm:
            raise HTTPException(status_code=429, detail="API key request limit reached. Retry in 60 seconds.")
        conn.execute("INSERT INTO api_key_requests(id,key_id,workspace_id,route,created_at) VALUES(?,?,?,?,?)",
                     (str(uuid.uuid4()), row["id"], row["workspace_id"], request.url.path, now))
        conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (now, row["id"]))
    request.state.workspace_id = row["workspace_id"]
    request.state.api_key_id = row["id"]
    return dict(row)


@app.get("/api/v1/public/models")
async def public_models(request: Request):
    _authenticate_api_key(request, "models:read")
    return await models()


@app.post("/api/v1/public/chat/completions")
async def public_chat_completions(payload: ChatRequest, request: Request):
    key = _authenticate_api_key(request, "chat:completions")
    result = await chat_completions(payload, request)
    _audit(key["workspace_id"], None, "api_key.chat", "model", payload.model,
           {"api_key_id": key["id"], "message_count": len(payload.messages)})
    return result


@app.get("/api/v1/audit-logs")
async def list_audit_logs(request: Request):
    with _db() as conn:
        rows = conn.execute("SELECT id,actor_user_id,action,resource_type,resource_id,details,created_at FROM audit_logs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 100",
                            (request.state.workspace_id,)).fetchall()
    return {"events": [{**dict(row), "details": _json.loads(row["details"])} for row in rows]}


# Workspace usage metering and configurable monthly quotas.
def _usage_counts(provider: str, usage: dict) -> tuple[int | None, int | None, int | None, float | None]:
    def number(*keys):
        for key in keys:
            value = usage.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                return int(value)
        return None
    if provider == "anthropic":
        prompt = number("input_tokens", "prompt_tokens")
        completion = number("output_tokens", "completion_tokens")
    elif provider == "google":
        prompt = number("promptTokenCount", "prompt_tokens")
        completion = number("candidatesTokenCount", "completion_tokens")
    else:
        prompt = number("prompt_tokens", "input_tokens")
        completion = number("completion_tokens", "output_tokens")
    total = number("total_tokens")
    if total is None and (prompt is not None or completion is not None):
        total = (prompt or 0) + (completion or 0)
    cost = usage.get("cost")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
        cost = usage.get("cost_usd")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
        cost = None
    return prompt, completion, total, float(cost) if cost is not None else None


def _month_start() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _check_workspace_quota(request: Request):
    workspace_id = getattr(request.state, "workspace_id", None)
    if not workspace_id:
        return
    with _db() as conn:
        limits = conn.execute("SELECT * FROM workspace_usage_limits WHERE workspace_id=?", (workspace_id,)).fetchone()
        if not limits:
            return
        since = _month_start()
        row = conn.execute("""SELECT COUNT(*) AS requests, COALESCE(SUM(total_tokens),0) AS tokens
            FROM usage_events WHERE workspace_id=? AND created_at>=? AND status='succeeded'""",
            (workspace_id, since)).fetchone()
    if limits["monthly_request_limit"] is not None and row["requests"] >= limits["monthly_request_limit"]:
        raise HTTPException(status_code=429, detail="Workspace monthly request quota reached.")
    if limits["monthly_token_limit"] is not None and row["tokens"] >= limits["monthly_token_limit"]:
        raise HTTPException(status_code=429, detail="Workspace monthly token quota reached.")


def _record_usage(request: Request, model_id: str, provider: str, usage: dict,
                  response_payload: dict, latency_ms: int, status: str):
    workspace_id = getattr(request.state, "workspace_id", None)
    if not workspace_id:
        return
    prompt, completion, total, cost = _usage_counts(provider, usage)
    with _db() as conn:
        conn.execute("""INSERT INTO usage_events
            (id,workspace_id,api_key_id,provider,model,prompt_tokens,completion_tokens,total_tokens,cost_usd,latency_ms,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), workspace_id, getattr(request.state, "api_key_id", None), provider,
             model_id, prompt, completion, total, cost, max(0, latency_ms), status, _now()))


@app.get("/api/v1/usage/summary")
async def usage_summary(request: Request):
    since = _month_start()
    with _db() as conn:
        rows = conn.execute("""SELECT provider,model,COUNT(*) AS requests,
            SUM(prompt_tokens) AS prompt_tokens,SUM(completion_tokens) AS completion_tokens,
            SUM(total_tokens) AS total_tokens,SUM(cost_usd) AS reported_cost_usd,
            AVG(latency_ms) AS average_latency_ms
            FROM usage_events WHERE workspace_id=? AND created_at>=? AND status='succeeded'
            GROUP BY provider,model ORDER BY requests DESC""", (request.state.workspace_id, since)).fetchall()
        limits = conn.execute("SELECT * FROM workspace_usage_limits WHERE workspace_id=?",
                              (request.state.workspace_id,)).fetchone()
        totals = conn.execute("""SELECT COUNT(*) AS requests,COALESCE(SUM(total_tokens),0) AS tokens,
            SUM(cost_usd) AS reported_cost_usd FROM usage_events
            WHERE workspace_id=? AND created_at>=? AND status='succeeded'""",
            (request.state.workspace_id, since)).fetchone()
    return {"period_start": since, "totals": dict(totals),
            "limits": dict(limits) if limits else {"monthly_token_limit": None, "monthly_request_limit": None},
            "by_model": [dict(row) for row in rows],
            "cost_note": "Costs are shown only when the upstream provider returns a numeric cost. Missing prices are null, never estimated."}


@app.put("/api/v1/usage/limits")
async def update_usage_limits(payload: dict = Body(...), request: Request = None):
    token_limit = payload.get("monthly_token_limit")
    request_limit = payload.get("monthly_request_limit")
    for value in (token_limit, request_limit):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise HTTPException(status_code=422, detail="Quota limits must be positive integers or null.")
    with _db() as conn:
        member = conn.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                              (request.state.workspace_id, request.state.user_id)).fetchone()
        if not member or member["role"] not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="Only workspace owners and admins can change quotas.")
        conn.execute("""INSERT INTO workspace_usage_limits(workspace_id,monthly_token_limit,monthly_request_limit,updated_at)
            VALUES(?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET
            monthly_token_limit=excluded.monthly_token_limit,monthly_request_limit=excluded.monthly_request_limit,
            updated_at=excluded.updated_at""",
            (request.state.workspace_id, token_limit, request_limit, _now()))
    _audit(request.state.workspace_id, request.state.user_id, "usage.limits.updated", "workspace",
           request.state.workspace_id, {"monthly_token_limit": token_limit, "monthly_request_limit": request_limit})
    return {"monthly_token_limit": token_limit, "monthly_request_limit": request_limit}


@app.get("/api/v1/usage/events")
async def usage_events(request: Request, limit: int = 100):
    if not 1 <= limit <= 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500.")
    with _db() as conn:
        rows = conn.execute("""SELECT id,api_key_id,provider,model,prompt_tokens,completion_tokens,total_tokens,
            cost_usd,latency_ms,status,created_at FROM usage_events WHERE workspace_id=?
            ORDER BY created_at DESC LIMIT ?""", (request.state.workspace_id, limit)).fetchall()
    return {"events": [dict(row) for row in rows]}


# Workspace membership administration (RBAC).
@app.get("/api/v1/workspace/members")
async def list_workspace_members(request: Request):
    with _db() as conn:
        rows = conn.execute("""SELECT u.id AS user_id,u.email,m.role,m.created_at
            FROM workspace_members m JOIN users u ON u.id=m.user_id
            WHERE m.workspace_id=? ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,u.email""",
            (request.state.workspace_id,)).fetchall()
    return {"members": [dict(row) for row in rows]}


@app.post("/api/v1/workspace/members")
async def add_workspace_member(payload: dict = Body(...), request: Request = None):
    target_user_id = payload.get("user_id")
    role = payload.get("role", "member")
    if not isinstance(target_user_id, str) or not target_user_id or not isinstance(role, str) or role not in {"admin", "member"}:
        raise HTTPException(status_code=422, detail="An existing user_id and role admin/member are required.")
    with _db() as conn:
        actor = conn.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                             (request.state.workspace_id, request.state.user_id)).fetchone()
        target = conn.execute("SELECT id FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not actor or actor["role"] not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="Workspace owner or admin role required.")
        if actor["role"] == "admin" and role != "member":
            raise HTTPException(status_code=403, detail="Admins may add members but cannot grant admin role.")
        if not target:
            raise HTTPException(status_code=404, detail="User not found.")
        try:
            conn.execute("INSERT INTO workspace_members(workspace_id,user_id,role,created_at) VALUES(?,?,?,?)",
                         (request.state.workspace_id, target_user_id, role, _now()))
        except _sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="User is already a workspace member.")
    _audit(request.state.workspace_id, request.state.user_id, "workspace.member.added",
           "workspace_member", target_user_id, {"role": role})
    return {"user_id": target_user_id, "role": role, "added": True}


@app.patch("/api/v1/workspace/members/{target_user_id}")
async def change_workspace_member_role(target_user_id: str, payload: dict = Body(...), request: Request = None):
    role = payload.get("role")
    if not isinstance(role, str) or role not in {"admin", "member"}:
        raise HTTPException(status_code=422, detail="Role must be admin or member.")
    with _db() as conn:
        actor = conn.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                             (request.state.workspace_id, request.state.user_id)).fetchone()
        target = conn.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                              (request.state.workspace_id, target_user_id)).fetchone()
        if not actor or actor["role"] != "owner":
            raise HTTPException(status_code=403, detail="Only the workspace owner can change member roles.")
        if not target or target["role"] == "owner":
            raise HTTPException(status_code=404, detail="Non-owner workspace member not found.")
        conn.execute("UPDATE workspace_members SET role=? WHERE workspace_id=? AND user_id=?",
                     (role, request.state.workspace_id, target_user_id))
    _audit(request.state.workspace_id, request.state.user_id, "workspace.member.role_changed",
           "workspace_member", target_user_id, {"role": role})
    return {"user_id": target_user_id, "role": role, "updated": True}


@app.delete("/api/v1/workspace/members/{target_user_id}")
async def remove_workspace_member(target_user_id: str, request: Request):
    with _db() as conn:
        actor = conn.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                             (request.state.workspace_id, request.state.user_id)).fetchone()
        target = conn.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                              (request.state.workspace_id, target_user_id)).fetchone()
        if not actor or actor["role"] not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="Workspace owner or admin role required.")
        if not target or target["role"] == "owner":
            raise HTTPException(status_code=404, detail="Non-owner workspace member not found.")
        if actor["role"] == "admin" and target["role"] != "member":
            raise HTTPException(status_code=403, detail="Admins may remove members but not admins.")
        conn.execute("DELETE FROM workspace_members WHERE workspace_id=? AND user_id=?",
                     (request.state.workspace_id, target_user_id))
    _audit(request.state.workspace_id, request.state.user_id, "workspace.member.removed",
           "workspace_member", target_user_id)
    return {"user_id": target_user_id, "removed": True}


def _require_workspace_role(request: Request, allowed_roles: set[str]):
    with _db() as conn:
        row = conn.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND user_id=?",
                           (request.state.workspace_id, request.state.user_id)).fetchone()
    if not row or row["role"] not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient workspace role for this operation.")
