# ThermaGuard on Vercel

Deploy the repository root, using the FastAPI framework. `pyproject.toml` selects
`api.main:app` rather than the archived Streamlit application and installs only
the API dependencies. Its build script builds React into `public/`; Vercel serves
the registered FastAPI frontend from its CDN, including the home page. The browser calls
the same origin's `/api/` routes. No API key belongs in the frontend.

## Enable protected DeepSeek chat

1. Create a persistent Upstash Redis database in your own account (not a temporary
   database). Keep it for the whole judging period. Disable eviction so the lifetime
   quota cannot be discarded under memory pressure. Use a separate database for
   development if you test locally.
2. In Vercel's project settings, add these **server-side secrets** to Production:
   `DEEPSEEK_API_KEY`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, and
   `CHAT_LIMIT_SECRET`. The last value should be a new random secret, generated
   privately with `python3 -c 'import secrets; print(secrets.token_hex(32))'`.
   Never prefix a credential with `VITE_`, commit it, or paste it into chat.
3. Set `CHAT_PROVIDER=deepseek` and `CHAT_MODEL=deepseek-flash`. Keep previews
   without provider credentials unless you intentionally budget for them.
4. Redeploy after changing environment variables. Check `/api/health` reports
   `chat_configured: true`, then test one short question in the assistant.

Defaults: 3 requests per visitor IP per 10-minute window, 20 requests site-wide
per UTC day, and 500 lifetime requests. Each request reserves quota before any
paid work, with up to 3 model calls, 1,200 output tokens per call, at most 4 tool
calls per round, 24,000 request bytes, 12 messages, and 4,000 characters per message.
The SDK has no automatic retries and a 30-second request timeout. Failed requests
also consume their reservation to prevent retry abuse. Fixed windows allow bursts
across a window boundary. Shared school/office IPs share the visitor limit.

Optional server settings: `CHAT_PER_IP_10_MIN`, `CHAT_DAILY_LIMIT`, and
`CHAT_LIFETIME_LIMIT`. Keep these low initially. They limit requests, **not dollars**.
Provider pricing and input lengths affect actual cost. Use a separate DeepSeek key
for this app and monitor its provider balance/usage. Revoke the key if compromised.

Redis atomically checks all quotas before incrementing any. The lifetime counter
`thermaguard:chat:lifetime` never expires; deleting it or resetting/replacing the
database resets that budget. Do not flush the database or enable eviction. Use one
database across production deployments so redeploying does not reset the counters.
Only HMAC hashes of visitor IPs are stored, with a short TTL; prompts and raw IPs
are not stored by this limiter. Vercel/provider logs have their own retention.

If Redis credentials are missing, invalid, or the service is unavailable, chat
fails closed before calling DeepSeek. Missing provider credentials disable chat
in the UI. When a quota is reached, chat returns a helpful limit message. The
NASA evidence and local model tools remain available independently of chat.

## Verify deployment

- Home page loads; no model results appear before submitting a tool form.
- `/api/health`, `/api/options`, the advisor, and both supported FLEX estimates work.
- A missing limiter or exhausted quota never calls the provider.
- A short chat question succeeds only after all server-side secrets are configured.
- Frontend assets and repository history contain no provider or Redis secrets.

Vercel account access is required to create the owned deployment. Free hosting does
not include free DeepSeek usage, guarantee uninterrupted uptime, or prevent an
attacker from exhausting the deliberately small chat quota. Keep the deployment
and Redis database owned by your accounts throughout judging.
