from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


class MCPRuntimeError(RuntimeError):
    pass


def validate_http_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise MCPRuntimeError("MCP HTTP endpoints must use HTTPS and must not embed credentials, query tokens, or fragments.")
    allowed = {item.strip().lower() for item in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if item.strip()}
    if not allowed or parsed.hostname.lower() not in allowed:
        raise MCPRuntimeError("The MCP host is not in the server-side MCP_ALLOWED_HOSTS allowlist.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise MCPRuntimeError("The MCP endpoint port is invalid.") from exc
    if port not in (None, 443):
        raise MCPRuntimeError("Only the default HTTPS port is permitted for remote MCP servers.")
    return endpoint


def stdio_config(config_key: str) -> dict:
    try:
        configured = json.loads(os.getenv("MCP_STDIO_SERVERS_JSON", "{}"))
    except ValueError as exc:
        raise MCPRuntimeError("MCP_STDIO_SERVERS_JSON is invalid.") from exc
    entry = configured.get(config_key) if isinstance(configured, dict) else None
    if not isinstance(entry, dict):
        raise MCPRuntimeError("This stdio server alias is not configured by the APOLO administrator.")
    command = entry.get("command")
    args = entry.get("args", [])
    env = entry.get("env", {})
    if (not isinstance(command, str) or not command or len(command) > 256
            or not isinstance(args, list) or len(args) > 32
            or not all(isinstance(x, str) and len(x) <= 2048 for x in args)):
        raise MCPRuntimeError("The administrator's stdio configuration is invalid.")
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise MCPRuntimeError("The administrator's stdio environment is invalid.")
    return {"command": command, "args": args, "env": env}


@asynccontextmanager
async def open_session(transport: str, endpoint: str | None = None, config_key: str | None = None):
    if transport == "streamable-http":
        if not endpoint:
            raise MCPRuntimeError("An HTTP endpoint is required.")
        validate_http_endpoint(endpoint)
        async with streamable_http_client(endpoint) as (read_stream, write_stream, _session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return
    if transport == "stdio":
        if not config_key:
            raise MCPRuntimeError("A server-side stdio alias is required.")
        cfg = stdio_config(config_key)
        params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env=cfg["env"])
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
        return
    raise MCPRuntimeError("Unsupported MCP transport.")


async def discover_tools(transport: str, endpoint: str | None = None, config_key: str | None = None) -> list[dict]:
    async with open_session(transport, endpoint, config_key) as session:
        result = await session.list_tools()
        tools = []
        for item in result.tools:
            tools.append({
                "name": item.name,
                "description": item.description or "",
                "input_schema": item.inputSchema if isinstance(item.inputSchema, dict) else {},
            })
        return tools


async def invoke_tool(transport: str, tool_name: str, arguments: dict, endpoint: str | None = None,
                      config_key: str | None = None) -> dict:
    async with open_session(transport, endpoint, config_key) as session:
        result = await session.call_tool(tool_name, arguments=arguments)
        content = []
        for item in result.content[:32]:
            if hasattr(item, "text"):
                content.append({"type": "text", "text": item.text[:8000]})
            elif hasattr(item, "mimeType"):
                content.append({"type": "binary", "mime_type": item.mimeType})
            else:
                content.append({"type": getattr(item, "type", "unknown")})
        structured = getattr(result, "structuredContent", None)
        return {"is_error": bool(result.isError), "content": content,
                "structured_content": structured if isinstance(structured, (dict, list, str, int, float, bool)) else None}
