from __future__ import annotations

import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "APOLO LangDock",
    instructions="Read-only discovery tools for APOLO LangDock. Provider billing and quotas remain controlled by each provider.",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8765")),
    streamable_http_path="/mcp",
)


@mcp.tool()
def apolo_service_info() -> dict:
    """Return public APOLO LangDock service and integration information."""
    return {
        "name": "APOLO LangDock",
        "version": "0.4.0",
        "capabilities": ["multi-provider-chat", "agents", "workflows", "mcp"],
        "license": "MIT",
        "pricing": "APOLO software has no subscription tier; model providers may charge for inference.",
    }


@mcp.tool()
def apolo_provider_catalog() -> list[dict]:
    """List supported model provider types and their billing characteristics."""
    return [
        {"id": "openrouter", "name": "OpenRouter", "policy": "Free routes may have changing limits and availability."},
        {"id": "google", "name": "Google AI", "policy": "Only eligible models and quotas may be free."},
        {"id": "openai", "name": "OpenAI", "policy": "API billing may apply."},
        {"id": "anthropic", "name": "Anthropic", "policy": "API billing may apply."},
        {"id": "ollama", "name": "Ollama", "policy": "Local inference; hardware and electricity are required."},
    ]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
