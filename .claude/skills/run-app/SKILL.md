---
name: run-app
description: Launch and drive the Conductor Voice Agent web server (FastAPI) in a fresh container. Use when asked to run, start, serve, or smoke-test the app locally.
---

# Run the Conductor Voice Agent

The app is a FastAPI server (`api/server.py`) that serves a web chat UI at
`/` plus REST/voice endpoints. It has two backends:

- **full mode** — `ConductorAgent`, backed by a ChromaDB knowledge base that
  must be ingested first (`python ingest.py`). Not available in a fresh
  container with no data.
- **minimal / cloud mode** — `MinimalConductor`, no ChromaDB, calls whatever
  LLM provider key is set. Selected automatically when any of
  `RENDER` / `RAILWAY` / `HEROKU` / `K_SERVICE` is in the environment.

For a smoke run, use **minimal mode** (`RENDER=1`).

## 1. Install dependencies

`api/server.py` imports `ConductorAgent` at module top level, which pulls in
`chromadb` and `tiktoken` **even in minimal mode** — so they're required just
to import the app, though minimal mode never uses them at runtime.

```bash
pip install fastapi 'uvicorn[standard]' pydantic pydantic-settings \
  python-dotenv openai python-multipart rich
# needed only so the module imports; not used in minimal mode:
pip install chromadb tiktoken
```

`rich` is included above because `utils/logger.py` imports it at module top,
and every entrypoint — including `api/server.py` — imports the logger; without
`rich` the app fails to import before it even reaches the chromadb/tiktoken
requirement.

If `pip` errors with "Cannot uninstall PyYAML … RECORD file not found" (the
Debian-managed system PyYAML), install PyYAML on its own with
`--ignore-installed` — keep it in a separate command, since `--ignore-installed`
applies to the **whole** install line and would otherwise force-reinstall the
packages above:

```bash
pip install --ignore-installed PyYAML
```

This repair only fixes PyYAML — it does **not** resume the install that
aborted. After running it, **re-run whichever `pip install` command above
failed**, so the packages it was installing (FastAPI, chromadb, …) actually
get installed before you launch.

## 2. Launch (minimal mode)

`RENDER=1` selects minimal mode. The listening port is set by `--port` on the
uvicorn CLI (the `PORT` env var only applies when running `python api/server.py`
directly, which reads it in `__main__`):

```bash
RENDER=1 python3 -m uvicorn api.server:app \
  --host 0.0.0.0 --port 8080 --log-level info > /tmp/server.log 2>&1 &
echo $! > /tmp/server.pid   # remember the PID so you can stop it before relaunching
```

Wait for readiness by polling `/health` (do not `sleep` blindly), then fail
fast if it never came up:

```bash
for i in $(seq 1 8); do
  curl -sf http://127.0.0.1:8080/health && break; sleep 1
done
curl -sf http://127.0.0.1:8080/health >/dev/null \
  || { echo "server did not start"; tail -20 /tmp/server.log; exit 1; }
```

## 3. Drive it

```bash
curl -s http://127.0.0.1:8080/health          # {"status":"healthy","mode":"minimal",...}
curl -s http://127.0.0.1:8080/ | head         # web chat UI (HTML)
curl -s -X POST http://127.0.0.1:8080/api/chat \
  -H 'Content-Type: application/json' -d '{"query":"Hello"}'
```

Screenshot the UI (pre-installed Chromium; use a mobile-ish viewport — the UI
is a PWA):

```bash
CHROME=$(ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
[ -x "$CHROME" ] || { echo "Chromium not found under /opt/pw-browsers"; exit 1; }
"$CHROME" --headless --no-sandbox --disable-gpu --screenshot=/tmp/ui.png \
  --window-size=430,900 --virtual-time-budget=6000 http://127.0.0.1:8080/
```

## Expected results without provider credentials

A fresh container has no LLM key, so these are expected — not failures:

- `/health` → `"providers":[]`, `"api_keys_configured":false`.
- `POST /api/chat` → a graceful *"Minimal mode: no AI provider configured…"*
  message (HTTP 200), **not** a real answer.
- `GET /api/voices` → **500**; the voice processor hard-requires
  `OPENAI_API_KEY` at init.
- The UI loads Tailwind from a CDN, which the container's outbound proxy
  blocks (SSL handshake errors in the log). Inline gradient/layout still
  render; only utility-class styling is missing.

## To get a real chat response

First install the SDK for the provider you'll use. The step-1 install only
covers OpenAI (the `openai` package, which also serves xAI/Grok). The other
providers import their SDK lazily, and `chat()` swallows a missing-SDK import
error and returns the "no provider configured"-style apology instead of a real
answer — so install the matching package first. `pip install -r
requirements-cloud.txt` pulls in all the provider SDKs at once, but it does
**not** include `chromadb`/`tiktoken`, so you still need the step-1 install to
import the app:

| Provider | Env var | Extra package |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | already installed |
| xAI / Grok | `XAI_API_KEY` | already installed (uses `openai`) |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic` |
| Google Gemini | `GOOGLE_API_KEY` | `google-generativeai` |
| AWS Bedrock | `AWS_REGION` + AWS creds | `boto3` |

Then set exactly one provider:

```bash
export OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY / GOOGLE_API_KEY / XAI_API_KEY
# AWS Bedrock Claude needs BOTH a region and valid AWS credentials — region
# alone is not enough:
#   export AWS_REGION=us-east-1
#   export AWS_ACCESS_KEY_ID=...      # plus AWS_SECRET_ACCESS_KEY,
#   export AWS_SECRET_ACCESS_KEY=...  # or an instance/role profile
```

Then **stop the smoke-test server and relaunch** — a running uvicorn process
won't pick up the newly exported key, and starting a second one just fails with
"address already in use" (while the readiness poll hits the stale server and
falsely reports success):

```bash
kill "$(cat /tmp/server.pid)" 2>/dev/null   # stop the old server
```

Now repeat step 2 (it records a fresh PID). Note: the environment's proxy AWS
variables (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` starting with `prox…`)
are placeholders and are rejected by Bedrock — they are not usable credentials.
