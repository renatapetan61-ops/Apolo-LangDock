# Model providers

APOLO LangDock routes requests through provider adapters. Add keys only to the server environment; never put secrets in browser variables.

## Supported adapter identifiers

| Model identifier | Provider | Key |
|---|---|---|
| `openrouter/<provider-model-id>` | OpenRouter | `OPENROUTER_API_KEY` |
| `google/<gemini-model-id>` | Google Gemini API | `GOOGLE_API_KEY` |
| `openai/<model-id>` | OpenAI | `OPENAI_API_KEY` |
| `anthropic/<model-id>` | Anthropic | `ANTHROPIC_API_KEY` |
| `ollama/<model-id>` | Ollama | No API key by default |
| `groq/<model-id>` | Groq | `GROQ_API_KEY` |
| `deepseek/<model-id>` | DeepSeek | `DEEPSEEK_API_KEY` |
| `mistral/<model-id>` | Mistral AI | `MISTRAL_API_KEY` |
| `xai/<model-id>` | xAI | `XAI_API_KEY` |

## Free usage

- Google provides a free Gemini API tier for selected models with limited access and rate limits. Availability varies by model, account, region, and current policy.
- OpenRouter marks selected model routes as free; those routes may have provider-specific rate limits and can change.
- Ollama runs open-weight models locally. Inference has no per-token API fee, but requires compatible hardware, memory, storage, and electricity.
- OpenAI and Anthropic API calls generally require billing. Their models must not be represented as free unless the provider explicitly offers a free quota for the specific account/model.

## Configuration

Copy `.env.example` to `.env` and add your own keys. Keep `.env` private and never commit it.

For local Ollama outside Docker, set `OLLAMA_BASE_URL` to an address reachable from the API container. The default `host.docker.internal` works in many Docker Desktop setups; Linux deployments may need an explicit host-gateway mapping.

## API example

```bash
curl http://localhost:8000/api/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "openrouter/openrouter/free",
    "messages": [{"role": "user", "content": "Olá!"}]
  }'
```

The API discovers models from configured providers and supports non-streaming and SSE chat for the OpenAI-compatible adapters, including Groq, DeepSeek, Mistral AI, and xAI. Provider-specific token usage is recorded when the upstream stream reports it; missing usage remains unknown rather than estimated. Optional `*_BASE_URL` overrides are available for the four additional adapters.
