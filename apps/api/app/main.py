from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="APOLO LangDock API",
    version="0.1.0",
    description="Open AI workspace API. Provider availability and free quotas are controlled by upstream providers.",
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROVIDERS = [
    {"id": "openai", "name": "OpenAI", "env_key": "OPENAI_API_KEY", "configured": bool(os.getenv("OPENAI_API_KEY")), "note": "Commercial models; free access is not guaranteed."},
    {"id": "anthropic", "name": "Anthropic", "env_key": "ANTHROPIC_API_KEY", "configured": bool(os.getenv("ANTHROPIC_API_KEY")), "note": "Commercial models; free access is not guaranteed."},
    {"id": "google", "name": "Google AI", "env_key": "GOOGLE_API_KEY", "configured": bool(os.getenv("GOOGLE_API_KEY")), "note": "Some models may have a limited free quota, subject to region and current terms."},
    {"id": "openrouter", "name": "OpenRouter", "env_key": "OPENROUTER_API_KEY", "configured": bool(os.getenv("OPENROUTER_API_KEY")), "note": "Includes selected free model routes with provider limits."},
    {"id": "ollama", "name": "Ollama (local)", "env_key": None, "configured": True, "note": "Open-weight models run on infrastructure you control; hardware required."},
]

class ChatRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]

@app.get("/")
async def root():
    return {"name": "APOLO LangDock API", "version": "0.1.0", "docs": "/docs"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "apolo-langdock-api"}

@app.get("/api/v1/providers")
async def providers():
    return {"providers": PROVIDERS}

@app.get("/api/v1/models")
async def models():
    # Catalog entries are intentionally conservative until provider adapters are implemented.
    return {
        "models": [
            {"id": "google/gemini-free", "provider": "google", "label": "Gemini (free quota if available)", "availability": "quota-dependent"},
            {"id": "openrouter/free", "provider": "openrouter", "label": "OpenRouter Free Router", "availability": "quota-dependent"},
            {"id": "ollama/local", "provider": "ollama", "label": "Local Ollama model", "availability": "local"},
        ]
    }

@app.post("/api/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    return {
        "error": {
            "type": "not_implemented",
            "message": "Provider adapters are the next milestone. Configure a provider key on the server; no model calls are faked by this endpoint.",
        },
        "requested_model": request.model,
    }
