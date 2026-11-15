# Local bug-testing setup

Clone the repository, then run the following from the repository root.

## Windows (PowerShell)

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r api/requirements.txt
Copy-Item .env.example .env  # First setup only; do not overwrite an existing .env.
```

## macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt
cp -n .env.example .env
```

Get the DeepSeek key from the project owner through a private channel, such as a
shared password-manager vault. Edit `.env` locally and fill in `DEEPSEEK_API_KEY`.
DeepSeek is selected automatically when its key is present. This is a one-time step on each computer. No real
credential is included in the repository or template.

Start the API in one terminal:

```sh
# Windows; use .venv/bin/python on macOS/Linux
.venv/Scripts/python -m uvicorn api.main:app --reload --port 8000
```

Start the UI in another terminal:

```sh
cd web
npm ci
npm run dev
```

Open http://localhost:5173. Check http://localhost:8000/api/health for
`chat_configured: true` and `chat_provider: "deepseek"`; this reports configuration,
not whether the provider accepts the key or the account has credits. Restart the
API after editing `.env`. Existing environment variables override the file. Data
exploration and predictions work without a provider key.

## Who can access the key?

`.gitignore` prevents ordinary Git adds of local environment files; it does not
encrypt secrets, change GitHub permissions, or remove secrets from Git history.
Anyone with repository read access can see committed content, even without push
access. Ignored files are not included when a collaborator clones or pulls.

Only `.env.example`, containing no real key, is tracked. Share the real key
privately with the collaborators who need it. Anyone given a shared key can copy
and use it; separate provider keys make revocation easier when available.

For automatic access without distributing the provider key, deploy an
authenticated backend, store the key on that server, and give collaborators
access to the backend. The current local API has no collaborator authentication;
do not expose it publicly as a substitute for this setup.

Never put a provider key in frontend code, browser storage, `VITE_` variables,
`.env.example`, or `.gitignore` itself. Files already tracked stay tracked even
after an ignore rule is added. If a real key was committed or publicly shared,
revoke it at the provider and replace it.
