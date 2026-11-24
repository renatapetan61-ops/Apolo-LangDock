# Webhook delivery worker

Webhook events are persisted in `webhook_deliveries` before the first network request. A delivery retains one immutable event envelope and delivery ID across retries, so receivers can deduplicate using `X-APOLO-Delivery`.

## Configuration

- Set `APOLO_MCP_ENCRYPTION_KEY` to a Fernet key.
- Set `WEBHOOK_ALLOWED_HOSTS` to exact destination hostnames, comma-separated.
- Set a long random `APOLO_WEBHOOK_WORKER_TOKEN` outside source control.
- Configure the destination endpoint using HTTPS on port 443.

## Dispatch

Schedule an external cron/job runner to call:

```http
POST /internal/webhooks/dispatch?limit=25
X-APOLO-Worker-Token: <worker-token>
```

Use a short interval (for example, once per minute). The worker only selects due, undelivered records and caps each batch at 100. Delivery retries use exponential backoff (30 seconds, 60 seconds, 120 seconds, and so on, capped at six hours) and stop after eight attempts. A row with no `delivered_at` and no `next_attempt_at` is exhausted or its endpoint is inactive; inspect `response_excerpt` before manually replaying it.

The worker endpoint is not enabled until a token is configured. Do not expose the token to browser code or commit it to the repository. Delivery is at-least-once: webhook consumers should be idempotent.
