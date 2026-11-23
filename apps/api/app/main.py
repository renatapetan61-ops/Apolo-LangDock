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
