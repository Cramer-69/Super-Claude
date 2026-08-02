# Conductor Super Agent

A local-first AI system that aggregates conversations from **Grok**, **ChatGPT**, **Gemini**, and **Antigravity** into a unified knowledge base with persistent memory across all your AI interactions.

## 🎯 Features

- **Multi-Platform Aggregation**: Combine conversations from all major AI platforms
- **Semantic Search**: RAG-based retrieval using ChromaDB vector database
- **Persistent Memory**: Never lose context across conversations
- **Code Snippet Extraction**: Automatically extracts and indexes code from all conversations
- **Privacy First**: Runs 100% locally on your machine
- **Rich CLI Interface**: Beautiful terminal interface with search and filtering
- **Optional Plugins**: mem0 for durable cross-session memory, Firecrawl for
  reading and searching the web — both off until you add a key
  ([Plugins](#-plugins))

## 🚀 Quick Start (Windows)

**Double-click `Start_Super_Agent.bat` on your Desktop.**

This will:

1. Auto-configure the environment
2. Install any missing dependencies (self-healing)
3. Launch the Multi-AI Super Agent interface

---

## 🤖 Supported Providers

- **Google Gemini** (Primary, Auto-configured)
- **Claude via AWS Bedrock** (Preferred Claude base)
- **Grok / xAI** (Added via Desktop key)
- **Perplexity** (Search enabled)
- **OpenAI** (Fallback)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd conductor_agent
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file and add your API keys:

```bash
copy .env.example .env
```

Edit `.env` and add either your AWS Bedrock settings or an API key:

```
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL_ID=anthropic.claude-3-5-haiku-20241022-v1:0
# or
OPENAI_API_KEY=sk-your-key-here
```

### 3. Export Your Conversations

#### ChatGPT

1. Go to [chat.openai.com](https://chat.openai.com)
2. Click your profile → Settings → Data Controls
3. Click "Export Data"
4. Download the ZIP file (you'll receive an email)
5. Extract `conversations.json`

#### Gemini

- **Method 1**: Use [Google Takeout](https://takeout.google.com)
  - Select "Gemini Apps Activity"
  - Download and extract
- **Method 2**: Save conversations as HTML
  - Open conversation in browser
  - Right-click → Save As → HTML

#### Grok/xAI

- Export from Grok settings (ZIP format)

#### Antigravity

- Conversations are automatically available at:

  ```
  C:\Users\<username>\.gemini\antigravity\brain
  ```

### 4. Ingest Your Data

Run the ingestion script to process and index your conversations:

```bash
# Ingest all platforms
python ingest.py --chatgpt "path/to/conversations.json" --gemini "path/to/gemini_export" --grok "path/to/grok_export.zip" --antigravity "C:/Users/jjc29/.gemini/antigravity/brain"

# Or just Antigravity (default)
python ingest.py

# Reset database and re-ingest
python ingest.py --reset --antigravity "C:/Users/jjc29/.gemini/antigravity/brain"
```

### 5. Start the CLI

```bash
python -m cli.interactive
```

## 💡 Usage Examples

### Basic Search

```
You: How did I implement authentication in previous projects?
```

### Search Code

```
You: /code python async patterns
```

### Platform-Specific Search

```
You: /platform chatgpt explain RAG architecture
```

### View Statistics

```
You: /stats
```

## 📁 Project Structure

```
conductor_agent/
├── config/              # Configuration management
│   └── settings.py
├── data_processors/     # Platform-specific processors
│   ├── base_processor.py
│   ├── chatgpt_processor.py
│   ├── gemini_processor.py
│   ├── grok_processor.py
│   └── antigravity_processor.py
├── knowledge_base/      # Vector store, retrieval and durable memory
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── memory.py       # mem0 plugin (cross-session memory)
│   └── retrieval.py
├── integrations/        # Optional third-party plugins
│   └── firecrawl_client.py  # Firecrawl plugin (web reading/search)
├── cli/                 # Command-line interface
│   └── interactive.py
├── utils/               # Utilities
│   └── logger.py
├── data/                # Data storage
│   ├── raw/            # Raw exports
│   ├── processed/      # Processed conversations
│   └── chroma_db/      # Vector database
├── ingest.py           # Data ingestion script
├── requirements.txt     # Python dependencies
└── .env.example        # Environment template
```

## 🔧 Configuration

All settings can be configured in `.env`:

```env
# LLM Configuration
CONDUCTOR_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# Vector Database
CHROMA_PERSIST_DIR=./data/chroma_db

# Search Parameters
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K=5

# Data Paths
ANTIGRAVITY_BRAIN_DIR=C:/Users/jjc29/.gemini/antigravity/brain
```

## 🔌 Plugins

Two optional plugins ship with the agent. Both are **inert until configured** —
no key means no client, no network calls, and no behavior change — and neither
can break a chat request: every call fails soft and logs a warning.

Install them with the normal requirements (`pip install -r requirements.txt`);
they are also in `requirements-cloud.txt`, so cloud deploys get them too. The
one exception is Vercel, whose serverless bundle (`api/requirements.txt`) ships
Firecrawl but not `mem0ai` — it would pull ~55 MB of vector-store dependencies
toward the 250 MB function limit for a backend that needs local storage a
serverless function doesn't have. Use Render, Cloud Run or Docker for durable
memory.

### mem0 — durable, cross-session memory

Remembers facts across conversations and folds them back into the system
prompt on later turns. Two backends:

```env
# Hosted mem0 platform — the key alone turns memory on
MEM0_API_KEY=m0-...

# ...or the self-hosted/OSS backend, which needs the explicit flag plus an
# OpenAI key for mem0's own LLM/embedder calls, and stores vectors locally
MEM0_ENABLED=true
OPENAI_API_KEY=sk-...

# Identity used when a caller doesn't pass user_id (see the warning below)
MEM0_DEFAULT_USER_ID=default
```

Memories are scoped per `user_id`. Pass one explicitly from any multi-user
caller — `chat()` logs a warning and falls back to the shared default user
otherwise, which would let memories leak between users. Stored memories are
sanitized and labelled as untrusted background data in the prompt, never as
instructions.

### Firecrawl — web reading and search

Lets the agent read pages and search the web via
[Firecrawl](https://firecrawl.dev):

```env
FIRECRAWL_API_KEY=fc-...

# Optional
FIRECRAWL_API_URL=http://localhost:3002   # self-hosted instance
FIRECRAWL_AUTO_FETCH_URLS=true            # read URLs mentioned in a query
FIRECRAWL_MAX_URLS_PER_QUERY=2
FIRECRAWL_MAX_CONTENT_CHARS=4000          # per-page cap sent to the model
FIRECRAWL_ALLOW_PRIVATE_HOSTS=false       # allow loopback/private targets
```

URLs pointing at loopback, private, link-local or otherwise reserved addresses
(including the cloud metadata endpoint) are refused before they reach the SDK.
Against the hosted API the fetch happens on Firecrawl's infrastructure anyway,
but a self-hosted instance runs inside your network, where a pasted link would
otherwise be an SSRF primitive. Set `FIRECRAWL_ALLOW_PRIVATE_HOSTS=true` only
when you deliberately crawl an internal site.

With auto-fetch on (the default once a key is set), any http(s) URL in a chat
query is scraped to markdown and added to the prompt, and the page shows up in
the response's `sources`. Fetched content is capped, stripped of control
characters and labelled as untrusted data — set `FIRECRAWL_AUTO_FETCH_URLS=false`
to keep the plugin available to the endpoints below without touching chat.

Two endpoints expose it directly (both return `503` when Firecrawl isn't
configured; `limit` is capped at 20 results per search):

```bash
curl -X POST localhost:8080/api/web/scrape \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://firecrawl.dev"}'

curl -X POST localhost:8080/api/web/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "firecrawl python sdk", "limit": 3}'
```

`FirecrawlClient.crawl(url, limit=...)` is available in Python for multi-page
crawls; it blocks until the crawl job finishes, so keep the limit small.

### LiveKit — realtime voice rooms

Mints join tokens for the browser client; the media path runs
browser ↔ LiveKit directly, so the server never proxies audio:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_TOKEN_TTL_SECONDS=3600   # optional
```

```bash
curl -X POST localhost:8080/api/livekit/token \
  -H 'Content-Type: application/json' \
  -d '{"identity": "user-1", "room": "ara"}'
# -> {"token": "...", "url": "wss://...", "room": "ara", "expires_in": 3600}
```

The grant is deliberately narrow — join that one room, publish and subscribe,
nothing else. No room-admin or room-create rights, so a leaked browser token
can't reshape the deployment. Identities and room names are restricted to
`A-Z a-z 0-9 . _ : -` (1–128 chars); anything else is refused with a 400.

### Dify — app backend

```env
DIFY_API_KEY=app-...
DIFY_API_URL=https://api.dify.ai/v1   # or your self-hosted instance
```

```bash
curl -X POST localhost:8080/api/dify/chat \
  -H 'Content-Type: application/json' \
  -d '{"query": "hello", "user": "user-1"}'
# -> {"answer": "...", "conversation_id": "...", "message_id": "..."}
```

Pass `conversation_id` back on the next call to continue the same Dify thread.

### OpenHands — agent runtime

```env
OPENHANDS_API_URL=http://localhost:3000
OPENHANDS_API_KEY=...   # optional, if your instance requires one
```

```bash
curl -X POST localhost:8080/api/openhands/conversations \
  -H 'Content-Type: application/json' \
  -d '{"task": "fix the failing test", "repository": "owner/repo"}'

curl localhost:8080/api/openhands/conversations/<conversation_id>
```

OpenHands' REST API is still moving, so responses are passed through as-is
rather than reshaped into a fixed schema.

## 🔗 OpenAI-compatible API (TypingMind, LibreChat, the `openai` SDK)

The server speaks enough of the OpenAI chat-completions API for any
OpenAI-compatible client to use the conductor as a custom model:

| Endpoint | Notes |
|---|---|
| `GET /v1/models` | Lists one model, `conductor` |
| `POST /v1/chat/completions` | `messages` and `stream` honored; sampling params accepted and ignored |

In **TypingMind** → Settings → Custom Models → add a model with:

- **Endpoint**: `https://your-host/v1/chat/completions`
- **Model ID**: `conductor`
- **API key**: whatever you set as `CONDUCTOR_API_KEY`

```bash
curl -X POST localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $CONDUCTOR_API_KEY" \
  -d '{"model": "conductor", "messages": [{"role": "user", "content": "hi"}]}'
```

Streaming (`"stream": true`) returns standard `chat.completion.chunk` SSE
events terminated by `data: [DONE]`. A request's optional `user` field scopes
mem0 memory to that end user.

**Set `CONDUCTOR_API_KEY` before exposing this publicly** — unset means no
auth (matching `/api/chat`), and these endpoints spend your LLM credits.
Because clients resend the whole conversation each turn, history is replayed
into the prompt and trimmed from the front at ~12k characters.

### Checking plugin status

`GET /health` reports both plugins, including which mem0 backend is live:

```json
{
  "plugins": {
    "mem0": {"configured": true, "enabled": true, "backend": "platform"},
    "firecrawl": {"configured": true, "enabled": true, "auto_fetch_urls": true},
    "livekit": {"configured": true, "enabled": true},
    "dify": {"configured": false, "enabled": false},
    "openhands": {"configured": false, "enabled": false}
  },
  "openai_compatible_api": {
    "models_endpoint": "/v1/models",
    "completions_endpoint": "/v1/chat/completions",
    "auth_required": true
  }
}
```

`configured` means the settings are present; `enabled` means the client
actually came up (a bad key, for instance, leaves it `false`).

## 🎨 CLI Commands

| Command | Description |
|---------|-------------|
| `<query>` | Ask any question |
| `/search <query>` | Search conversations |
| `/code <query>` | Search code snippets |
| `/platform <name> <query>` | Search specific platform |
| `/stats` | Show database statistics |
| `/clear` | Clear screen |
| `/help` | Show help |
| `/exit` | Exit application |

## 🔍 How It Works

1. **Data Processing**: Platform-specific processors parse and standardize conversations
2. **Embedding Generation**: Text is chunked and converted to semantic embeddings (OpenAI)
3. **Vector Storage**: Embeddings stored in ChromaDB for fast similarity search
4. **Retrieval**: Hybrid search with re-ranking by recency and relevance
5. **Context**: Retrieved conversations provide context for queries

## 🛠️ Troubleshooting

### "No relevant conversations found"

- Ensure you've run `ingest.py` to load your data
- Check that your export files are in the correct format
- Run `/stats` to verify database has content

### API Key Errors

- Verify `OPENAI_API_KEY` is set in `.env`
- Ensure the key has sufficient credits

### Import Errors

- Run `pip install -r requirements.txt`
- Ensure Python 3.9+ is installed

## 📊 Performance

- **Embedding Generation**: ~1000 tokens/second with caching
- **Search Speed**: <500ms for most queries
- **Storage**: ~1MB per 100 conversations
- **Cost**: ~$0.10 per 1000 conversations (embeddings)

## 🔐 Privacy

- **100% Local**: All data stays on your machine
- **No Telemetry**: ChromaDB telemetry disabled
- **API Calls**: Only for embeddings (text only, no PII)

## 🚀 Deploy

The web/voice API in `api/server.py` runs anywhere a Python container runs. The
recommended target is **Google Cloud Run** with the API key stored in **Secret
Manager**. Local Docker and Render also work.

### Required env vars

At least one LLM provider configuration:

| Variable | Where to get it |
|---|---|
| `AWS_REGION` | Your AWS Bedrock region, e.g. `us-east-1` |
| `AWS_BEDROCK_MODEL_ID` | Optional Bedrock Claude model override |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys |
| `GOOGLE_API_KEY` | https://aistudio.google.com/app/apikey |

Optional plugin keys (see [Plugins](#-plugins)); leave them unset to deploy
without either plugin:

| Variable | Where to get it |
|---|---|
| `MEM0_API_KEY` | https://app.mem0.ai/dashboard/api-keys |
| `FIRECRAWL_API_KEY` | https://www.firecrawl.dev/app/api-keys |

The container binds to `0.0.0.0:${PORT}` (default `8080`). Cloud Run / Render
inject `PORT` automatically.

### Local Docker

```bash
docker build -t conductor-agent .
docker run --rm -p 8080:8080 -e OPENAI_API_KEY=sk-... conductor-agent
# or pass a whole .env file:
docker run --rm -p 8080:8080 --env-file .env conductor-agent
```

Open http://localhost:8080 and check `/health` — `api_keys_configured` should be
`true`.

### Google Cloud Run (recommended)

One-time setup (replace `$PROJECT_ID`):

```bash
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

# Store the key in Secret Manager
echo -n "sk-your-openai-key" | \
  gcloud secrets create openai-api-key --data-file=-

# Grant the Cloud Run runtime SA access (project-default Compute SA)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding openai-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

Build + deploy:

```bash
gcloud run deploy conductor-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest
```

The deploy URL appears at the end. Hit `/health` to confirm
`api_keys_configured: true`.

### GitHub + Cloudflare + Cloud Run rollout

Recommended order:

1. Push this repository to GitHub.
2. Deploy the container to Cloud Run.
3. Put your domain on Cloudflare and point a subdomain at the Cloud Run service.

Keep `.env` local only. This repo already ignores `.env` in `.gitignore`, so
only commit `.env.example`.

### Cloudflare custom domain

After Cloud Run is working, connect Cloudflare in front of it:

1. Add your domain to Cloudflare.
2. In Google Cloud Run, add a custom domain mapping for your app hostname
   (for example `app.example.com`).
3. In Cloudflare DNS, create the record Cloud Run asks for.
4. Keep SSL enabled in Cloudflare and verify the app over HTTPS.
5. Test `/health` through the Cloudflare hostname before sharing the app.

Use this approach if your goal is to get the existing Python app live behind
Cloudflare without rewriting it.

### Cloudflare Workers / workers-sdk

This repository is **not** a drop-in Cloudflare Workers app. The current
deployment model is a long-running Python web server started from
`api/server.py` with Gunicorn/Uvicorn. There is no Worker entrypoint, Wrangler
configuration, or Workers-compatible runtime layer in this repo today.

If you want Cloudflare Workers, treat that as a future migration or edge-layer
project rather than a simple deploy target swap.

To rotate the key:

```bash
echo -n "sk-new-key" | \
  gcloud secrets versions add openai-api-key --data-file=-
gcloud run services update conductor-agent --region us-central1 \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest
```

### Render

The repo includes `render.yaml`. In the Render dashboard set `OPENAI_API_KEY`
under **Environment** — do not commit it. Render injects `PORT` automatically.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `502` / "service unavailable" on Cloud Run | Container didn't bind to `$PORT`. Ensure you're using the Dockerfile in this repo (shell-form `CMD`). |
| Logs show `No LLM API key is configured` | Set `OPENAI_API_KEY` (or `--set-secrets`) and redeploy. |
| `/api/chat` returns 500 | Check `/health` — if `api_keys_configured: false`, the key isn't reaching the container. |
| `FileNotFoundError` for `antigravity_brain_dir` | Leave `ANTIGRAVITY_BRAIN_DIR` blank unless you actually have that folder. |

## 🚧 Future Enhancements

- [x ] LangGraph conductor orchestration with specialized sub-agents
- [ x] Web UI interface
- [x ] Support for more platforms (Claude, Perplexity)
- [ x] Real-time conversation sync
- [x ] Export to NotebookLM format
- [x ] Conversation analytics and insights

## 📝 License

MIT License - Feel free to use and modify

## 🤝 Contributing

This is a personal project, but feel free to fork and adapt for your needs!

---

**Built with**: Python, ChromaDB, OpenAI, LangChain, Rich CLI
