# MCP OAuth 2.1 integration plan

## Current state

APOLO LangDock currently supports encrypted, workspace-scoped bearer credentials for Streamable HTTP MCP servers. This is not OAuth 2.1. Stdio servers continue to use administrator-configured environment aliases and must not use the HTTP OAuth flow.

## Required protocol behavior

The implementation must follow the MCP HTTP authorization profile:
- Discover Protected Resource Metadata (RFC 9728) and Authorization Server Metadata (RFC 8414) or OpenID Connect discovery.
- Require HTTPS for the MCP resource and authorization endpoints.
- Use Authorization Code with PKCE S256 for interactive public clients.
- Validate state, authorization response issuer when advertised, metadata issuer, exact registered redirect URI, and resource/audience binding (RFC 8707).
- Send access tokens only in the Authorization header; never in query strings.
- Never forward an incoming MCP access token to a different upstream service.
- Encrypt access and refresh tokens at rest; rotate refresh tokens where supported.
- Keep bearer-token authentication as an explicit compatibility mode, not a fallback after OAuth failure.

## Planned API lifecycle

1. POST /api/v1/mcp/servers/{server_id}/oauth/start creates a short-lived, one-time authorization transaction and returns the authorization URL.
2. The browser follows the authorization URL at the external identity provider.
3. GET /api/v1/mcp/oauth/callback validates state and issuer, exchanges the code using the stored PKCE verifier, and stores encrypted tokens.
4. POST /api/v1/mcp/servers/{server_id}/oauth/revoke clears local tokens and invokes provider revocation when supported.
5. Discovery and tool calls use the OAuth token provider and refresh flow without exposing tokens to the browser.

## Implementation gates

- Do not ship a partial redirect flow that accepts arbitrary callback URLs or skips PKCE, state, issuer, or audience validation.
- The OAuth transaction store must work across API workers and restarts; process-local futures are not acceptable for production.
- Callback URLs must be configured explicitly and use HTTPS in production.
- OAuth tokens, authorization codes, client secrets, and PKCE verifiers must never enter audit logs.
- Add tests for state mismatch, issuer mismatch, missing PKCE support, invalid audience, expired tokens, refresh rotation, replayed callback, and workspace isolation.

## References

- MCP authorization specification: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/authorization.mdx
- MCP Python SDK OAuth client guide: https://py.sdk.modelcontextprotocol.io/v1/client/oauth-clients/
- RFC 9728 Protected Resource Metadata: https://www.rfc-editor.org/rfc/rfc9728
- RFC 8707 Resource Indicators: https://www.rfc-editor.org/rfc/rfc8707
