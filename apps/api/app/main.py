from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="APOLO LangDock API",
    version="0.2.0",
    description="Open AI workspace API. Provider availability and free quotas are controlled by upstream providers.",
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

PROVIDERS = [
    {"id": "openai", "name": "OpenAI", "configured": bool(os.getenv("OPENAI_API_KEY")), "free_policy": "Paid API; requires your own key and billing."},
    {"id": "anthropic", "name": "Anthropic", "configured": bool(os.getenv("ANTHROPIC_API_KEY")), "free_policy": "Paid API; requires your own key and billing."},
    {"id": "google", "name": "Google AI", "configured": bool(os.getenv("GOOGLE_API_KEY")), "free_policy": "Some models may have limited free quota; region and terms apply."},
    {"id": "openrouter", "name": "OpenRouter", "configured": bool(os.getenv("OPENROUTER_API_KEY")), "free_policy": "Selected free model routes may have rate and availability limits."},
    {"id": "ollama", "name": "Ollama (local)", "configured": True, "free_policy": "Local inference; hardware and electricity are user's responsibility."},
]

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=1024, ge=1, le=32768)

def _messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]

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
    return {"name": "APOLO LangDock API", "version": "0.2.0", "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "apolo-langdock-api"}

@app.get("/api/v1/providers")
async def providers():
    return {"providers": PROVIDERS}

@app.get("/api/v1/models")
async def models():
    return {"models": [
        {"id": "openrouter/openrouter/free", "provider": "openrouter", "label": "OpenRouter Free Router", "availability": "quota-dependent"},
        {"id": "google/gemini-2.5-flash", "provider": "google", "label": "Gemini 2.5 Flash", "availability": "provider-quota-dependent"},
        {"id": "ollama/llama3.2", "provider": "ollama", "label": "Llama 3.2 (local)", "availability": "local"},
        {"id": "openai/gpt-4.1-mini", "provider": "openai", "label": "GPT-4.1 mini", "availability": "paid-key-required"},
        {"id": "anthropic/claude-3-5-haiku-latest", "provider": "anthropic", "label": "Claude Haiku", "availability": "paid-key-required"}
    ]}

@app.post("/api/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    provider, separator, model = request.model.partition("/")
    if not separator or not model:
        raise HTTPException(status_code=400, detail="Use provider/model as the model identifier.")

    body: dict[str, Any] = {"messages": _messages(request.messages), "temperature": request.temperature, "max_tokens": request.max_tokens}

    if provider == "openrouter":
        key = os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="Configure OPENROUTER_API_KEY on the server.")
        result = await _post_openai_compatible("https://openrouter.ai/api/v1", key, model, body)
    elif provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="Configure OPENAI_API_KEY on the server. This provider may incur charges.")
        result = await _post_openai_compatible("https://api.openai.com/v1", key, model, body)
    elif provider == "ollama":
        result = await _post_openai_compatible(os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"), None, model, body)
    elif provider == "google":
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="Configure GOOGLE_API_KEY on the server. Free quota depends on Google's current terms and region.")
        contents = [{"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]} for m in request.messages]
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": key},
                json={"contents": contents, "generationConfig": {"temperature": request.temperature, "maxOutputTokens": request.max_tokens}},
            )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"provider_error": response.text[:1200], "status": response.status_code})
        data = response.json()
        answer = "".join(part.get("text", "") for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []))
        result = {"id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion", "created": int(time.time()), "model": request.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}]}
    elif provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise HTTPException(status_code=503, detail="Configure ANTHROPIC_API_KEY on the server. This provider may incur charges.")
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": model, "max_tokens": request.max_tokens, "temperature": request.temperature, "messages": [{"role": m.role, "content": m.content} for m in request.messages if m.role in ("user", "assistant")]},
            )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"provider_error": response.text[:1200], "status": response.status_code})
        data = response.json()
        answer = "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
        result = {"id": data.get("id", f"chatcmpl-{uuid.uuid4().hex}"), "object": "chat.completion", "created": int(time.time()), "model": request.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": data.get("stop_reason", "stop")}]}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    return result
