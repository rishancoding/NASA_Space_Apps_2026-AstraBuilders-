# ThermaGuard on Vercel

Deploy the repository root using the FastAPI framework. `pyproject.toml` selects
`api.main:app` rather than the archived Streamlit application and installs the API
dependencies. The build script builds React into `public/`; the registered FastAPI
frontend is served from Vercel's CDN. The browser calls same-origin `/api/` routes.

## Protected DeepSeek chat — no Upstash

Store `DEEPSEEK_API_KEY` as a server-side Production Secret in Vercel. Set
`CHAT_PROVIDER=deepseek` and `CHAT_MODEL=deepseek-flash`. Never use a `VITE_`
variable for credentials or commit a key. Keep previews without provider keys.

The Vercel project must have a published, enabled firewall rule:

- Name: `ThermaGuard chat rate limit`
- Condition: path starts with `/api/chat`
- Action: rate limit, fixed window
- Limit: **10 requests per IP per 600 seconds (10 minutes)**
- Exceeded action: rate limit (HTTP 429)

Once the rule is published, set server-only Production Config
`CHAT_FIREWALL_PROTECTED=1` and redeploy. Missing that flag or the Vercel platform
marker disables chat before any paid model call. The flag records deployment
configuration; it does not check the firewall on every request. If the rule is
removed, disable the flag and redeploy too. Frontend headers cannot enable chat.

The rule lives in the Vercel project's firewall configuration, separately from
`vercel.json`. Review it after moving this app to another project. All deployment
URLs in this project are covered by the published project firewall rule.

Vercel's counters are per IP and per region, with fixed windows. Shared school or
office IPs share the limit; multiple IPs, regions, or adjacent windows can permit
more traffic. This reduces abuse but is **not a daily, lifetime, or dollar cap**.
The earlier Redis quotas are removed. No Upstash account or database is needed.
Monitor DeepSeek usage/balance and revoke the dedicated app key if necessary.

Each chat request is additionally limited to 24,000 bytes, 12 messages and 4,000
characters per message. It can make at most 3 model calls with 1,200 output tokens
per call and at most 4 local tool calls per DeepSeek round. The provider SDK has
no automatic retries and a 30-second request timeout. These limits do not turn
paid DeepSeek usage into free usage.

## Verification

Check the public homepage and `/api/health`. With the key and protection configured,
`chat_configured` should be true. Test one short question. Test throttling with
invalid chat requests (for example an empty messages array), which reach the
firewall but never invoke the paid provider; excess requests should receive 429.
The material advisor, NASA explorer and local model tools work without AI.

Local API chat stays off; the local data and model workspaces remain available.
Do not set a fake Vercel marker to expose a local server without edge protection.

References: https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting
