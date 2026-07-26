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

For a minimal-mode smoke run you only need the lightweight web + provider
deps — the same set as `requirements-cloud.txt`:

```bash
pip install -r requirements-cloud.txt
# or, explicitly:
pip install fastapi 'uvicorn[standard]' pydantic pydantic-settings \
  python-dotenv openai python-multipart rich
```

`rich` is required because `utils/logger.py` imports it at module top, and
every entrypoint — including `api/server.py` — imports the logger; without
`rich` the app fails to import.

**`chromadb` + `tiktoken` are only needed for full/local mode.** `api/server.py`
imports `ConductorAgent` lazily (inside `get_conductor()`), so importing and
starting the app in minimal mode does **not** pull in ChromaDB. Install these
two only if you plan to run the full memory-backed conductor:

```bash
pip install chromadb tiktoken   # full/local mode only
```

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
failed**, so the packages it was installing actually get installed before you
launch.

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

Make sure the SDK for your chosen provider is installed. `requirements-cloud.txt`
already includes all of them, so if you installed that in step 1 you're covered.
If you used the explicit minimal list instead, it only has `openai` (which also
serves xAI/Grok) — install the extra package from the table below for any other
provider. Each non-OpenAI provider imports its SDK lazily; if it's missing,
`chat()` catches the `ModuleNotFoundError` and returns a **provider-failed**
message — e.g. `Sorry — the anthropic provider failed: ModuleNotFoundError: No module named 'anthropic'`
— rather than a real answer. (That's a *different* message from the
"Minimal mode: no AI provider configured…" one, which only appears when no
provider key is set at all.)

| Provider | Env var | SDK (in `requirements-cloud.txt`) |
|---|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | `anthropic` |
| xAI / Grok | `XAI_API_KEY` | `openai` (same client) |
| OpenAI | `OPENAI_API_KEY` | `openai` |
| Google Gemini | `GOOGLE_API_KEY` | `google-generativeai` |
| AWS Bedrock | `AWS_REGION` + AWS creds | `boto3` |

**Provider precedence:** direct/"home field" APIs win, in the order above —
Claude via the Anthropic API, Grok via xAI, then OpenAI, then Google. **Bedrock
is a last resort**, used only when no direct provider key is set, so having AWS
credentials in the environment does not silently route Claude through Bedrock.

Then set the provider you want (Claude shown):

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Claude, direct Anthropic API (recommended)
# or: export XAI_API_KEY=xai-...      # Grok, direct xAI API
# or: export OPENAI_API_KEY=sk-...    # or GOOGLE_API_KEY=...
# Bedrock (last resort — only if no direct key is set) needs a region AND
# valid AWS credentials:
#   export AWS_REGION=us-east-1
#   export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...   # or an IAM role
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
