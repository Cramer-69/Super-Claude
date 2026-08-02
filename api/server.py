"""
FastAPI server for voice-enabled conductor agent.
Provides REST API and web interface for mobile access.
"""

import os
import sys
import uuid
from pathlib import Path

# Add conductor_agent directory to sys.path so bare internal imports work
_pkg_dir = str(Path(__file__).resolve().parent.parent)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
import json
import secrets
import time
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
# NOTE: ConductorAgent is imported lazily inside get_conductor() (full mode
# only). It pulls in ChromaDB, which is intentionally excluded from
# requirements-cloud.txt; importing it here would break cloud/minimal
# deploys (Render, Cloud Run, Bedrock) on startup with ModuleNotFoundError.
from voice.voice_processor import get_voice_processor
from integrations.firecrawl_client import get_firecrawl_client
from integrations.livekit_client import get_livekit_client
from integrations.dify_client import get_dify_client
from integrations.openhands_client import get_openhands_client
from knowledge_base.memory import get_memory_store
from utils.logger import logger
from config.settings import settings

# Initialize FastAPI app
app = FastAPI(
    title="Conductor Voice Agent",
    description="Voice-enabled AI assistant with persistent memory",
    version="1.0.0"
)

# Add CORS middleware for mobile access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for mobile
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (lazy initialization to avoid startup crashes)
conductor = None
voice_processor = None


_CLOUD_ENV_VARS = ("K_SERVICE", "RENDER", "RAILWAY", "HEROKU", "VERCEL")


def _is_cloud() -> bool:
    """True on Cloud Run / Render / Railway / Heroku / Vercel — skip ChromaDB."""
    return any(os.getenv(v) for v in _CLOUD_ENV_VARS)



def get_conductor():
    """Lazy initialization of conductor agent."""
    global conductor
    if conductor is None:
        # Use minimal conductor in cloud environments (no ChromaDB)
        is_cloud = _is_cloud()

        try:
            if is_cloud:
                from conductor.minimal import MinimalConductor
                conductor = MinimalConductor()
                logger.info("Using minimal conductor (cloud mode - no memory)")
            else:
                # Imported here (not at module top) so cloud/minimal deploys
                # don't require ChromaDB just to import the app.
                from conductor.agent import ConductorAgent
                conductor = ConductorAgent()
                logger.info("Using full conductor (local mode - with memory)")
        except Exception as e:
            logger.error(f"Failed to initialize conductor: {e}")
            # Ultimate fallback - minimal conductor
            try:
                from conductor.minimal import MinimalConductor
                conductor = MinimalConductor()
                logger.info("Fallback to minimal conductor due to error")
            except Exception:
                raise ValueError(f"Could not initialize any conductor: {e}")
    return conductor



def get_voice_processor_instance():
    """Lazy initialization of voice processor."""
    global voice_processor
    if voice_processor is None:
        voice_processor = get_voice_processor()
    return voice_processor


# Create temp directory for audio files. Use the system temp dir (writable
# everywhere, including serverless/read-only filesystems like Vercel where
# only /tmp is writable) instead of a relative path in a read-only CWD.
import tempfile

TEMP_DIR = Path(tempfile.gettempdir()) / "conductor_audio"
try:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    logger.warning(
        f"Could not create audio temp dir {TEMP_DIR}: {exc}; "
        "voice endpoints may be unavailable"
    )


# Upper bound for /api/web/search results per request.
MAX_WEB_SEARCH_LIMIT = 20


# Request/Response Models
class ChatRequest(BaseModel):
    query: str
    platform_filter: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    sources: list
    audio_url: Optional[str] = None


class VoiceSettings(BaseModel):
    voice: str = "nova"


class ScrapeRequest(BaseModel):
    url: str


class WebSearchRequest(BaseModel):
    query: str
    # Capped: each result costs Firecrawl credits and request latency, so an
    # unbounded limit is an easy way to run up a bill or stall a worker.
    limit: int = Field(default=5, ge=1, le=MAX_WEB_SEARCH_LIMIT)


class LiveKitTokenRequest(BaseModel):
    identity: str
    room: str


class DifyChatRequest(BaseModel):
    query: str
    user: str
    conversation_id: Optional[str] = None
    inputs: Optional[dict] = None


class OpenHandsTaskRequest(BaseModel):
    task: str
    repository: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """The subset of OpenAI's chat-completions request this server honors.

    Sampling knobs (temperature, top_p, ...) are accepted and ignored — the
    conductor picks its own — so clients that always send them still work.
    """
    model: Optional[str] = None
    messages: List[ChatMessage]
    stream: bool = False
    user: Optional[str] = None

    model_config = {"extra": "ignore"}


# In-memory voice settings (could be persisted later)
current_voice_settings = VoiceSettings()


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main web interface."""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"

    if index_file.exists():
        with open(index_file, 'r', encoding='utf-8') as f:
            return f.read()
    return """
        <html>
            <body>
                <h1>Conductor Voice Agent</h1>
                <p>Web interface will be available soon.</p>
                <p>API is running. Try POST /api/chat</p>
            </body>
        </html>
        """


@app.on_event("startup")
async def _startup_log_config():
    """Log API-key configuration so missing keys are obvious in cloud logs."""
    providers = settings.configured_providers()
    if providers:
        logger.info(f"Configured LLM providers: {', '.join(providers)}")
    else:
        logger.warning(
            "No LLM provider configured. The /api/chat endpoint will fail "
            "until AWS_REGION (for Bedrock Claude) or another provider key is set. "
            "See README -> Deploy."
        )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    providers = settings.configured_providers()
    memory = get_memory_store()
    return {
        "status": "healthy",
        "service": "conductor-voice-agent",
        "version": "1.0.0",
        "mode": "minimal" if _is_cloud() else "full",
        "providers": providers,
        "api_keys_configured": bool(providers),
        "plugins": {
            "mem0": {
                "configured": settings.mem0_configured(),
                "enabled": memory.enabled,
                "backend": memory.backend,
            },
            "firecrawl": {
                "configured": settings.firecrawl_configured(),
                "enabled": get_firecrawl_client().enabled,
                "auto_fetch_urls": settings.firecrawl_auto_fetch_urls,
            },
            "livekit": {
                "configured": settings.livekit_configured(),
                "enabled": get_livekit_client().enabled,
            },
            "dify": {
                "configured": settings.dify_configured(),
                "enabled": get_dify_client().enabled,
            },
            "openhands": {
                "configured": settings.openhands_configured(),
                "enabled": get_openhands_client().enabled,
            },
        },
        "openai_compatible_api": {
            "models_endpoint": "/v1/models",
            "completions_endpoint": "/v1/chat/completions",
            "auth_required": bool(settings.conductor_key()),
        },
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Text-based chat endpoint.

    Args:
        request: Chat request with query and optional platform filter

    Returns:
        Chat response with answer and sources
    """
    try:
        logger.info(f"Chat request: {request.query[:100]}...")

        result = get_conductor().chat(
            query=request.query,
            platform_filter=request.platform_filter
        )

        return ChatResponse(
            response=result['response'],
            sources=result['sources']
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _require_plugin_auth(authorization: Optional[str]) -> None:
    """Gate the plugin routes on CONDUCTOR_API_KEY when one is configured.

    These routes spend money or act with the server's credentials — a
    Firecrawl scrape, a Dify message, a LiveKit publish token, an
    OpenHands task — so they must not stay open when the operator has
    told the server it is exposed. Unset means open, matching /api/chat
    and the existing web UI.
    """
    _require_conductor_key(authorization)


def _require_firecrawl():
    """Return an enabled Firecrawl client or fail with an actionable 503."""
    client = get_firecrawl_client()
    if not client.enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Firecrawl is not available. Install firecrawl-py and set "
                "FIRECRAWL_API_KEY (or FIRECRAWL_API_URL for a self-hosted "
                "instance). See README -> Plugins."
            ),
        )
    return client


@app.post("/api/web/scrape")
async def web_scrape(
    request: ScrapeRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Read a single web page as markdown via Firecrawl.

    Args:
        request: Scrape request with the page URL

    Returns:
        The page's url, title and markdown content
    """
    _require_plugin_auth(authorization)
    page = _require_firecrawl().scrape(request.url)
    if page is None:
        raise HTTPException(status_code=502, detail=f"Could not read {request.url}")
    return page


@app.post("/api/web/search")
async def web_search(
    request: WebSearchRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Search the web via Firecrawl.

    Args:
        request: Search request with the query and a result limit

    Returns:
        A list of {url, title, content} results
    """
    _require_plugin_auth(authorization)
    results = _require_firecrawl().search(request.query, limit=request.limit)
    return {"query": request.query, "results": results}


def _plugin_unavailable(name: str, hint: str) -> HTTPException:
    """503 with the settings that would turn `name` on."""
    return HTTPException(
        status_code=503,
        detail=f"{name} is not configured. {hint} See README -> Plugins.",
    )


@app.post("/api/livekit/token")
async def livekit_token(
    request: LiveKitTokenRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Mint a LiveKit join token for the browser client.

    Args:
        request: The participant identity and the room to join

    Returns:
        The token, the LiveKit server URL, and the token's lifetime
    """
    _require_plugin_auth(authorization)
    client = get_livekit_client()
    if not client.enabled:
        raise _plugin_unavailable(
            "LiveKit",
            "Install livekit-api and set LIVEKIT_URL, LIVEKIT_API_KEY and "
            "LIVEKIT_API_SECRET.",
        )
    grant = client.access_token(request.identity, request.room)
    if grant is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not mint a token. identity and room must be 1-128 "
                "characters of A-Z a-z 0-9 . _ : -"
            ),
        )
    return grant


@app.post("/api/dify/chat")
async def dify_chat(
    request: DifyChatRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Send a message to the configured Dify app.

    Args:
        request: The query, the end-user id, and an optional conversation
            id to continue an existing Dify conversation

    Returns:
        The app's answer plus its conversation and message ids
    """
    _require_plugin_auth(authorization)
    client = get_dify_client()
    if not client.enabled:
        raise _plugin_unavailable("Dify", "Set DIFY_API_KEY (and DIFY_API_URL if self-hosted).")
    result = client.chat(
        request.query,
        user=request.user,
        conversation_id=request.conversation_id,
        inputs=request.inputs,
    )
    if result is None:
        raise HTTPException(status_code=502, detail="Dify request failed")
    return result


@app.post("/api/openhands/conversations")
async def openhands_start(
    request: OpenHandsTaskRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    Hand a task to OpenHands, starting a new conversation.

    Args:
        request: The task text and an optional repository to work in

    Returns:
        The OpenHands server's response, passed through as-is
    """
    _require_plugin_auth(authorization)
    client = get_openhands_client()
    if not client.enabled:
        raise _plugin_unavailable("OpenHands", "Set OPENHANDS_API_URL.")
    result = client.start_conversation(request.task, repository=request.repository)
    if result is None:
        raise HTTPException(status_code=502, detail="OpenHands request failed")
    return result


@app.get("/api/openhands/conversations/{conversation_id}")
async def openhands_status(
    conversation_id: str,
    authorization: Optional[str] = Header(default=None),
):
    """
    Read one OpenHands conversation's state.

    Args:
        conversation_id: The conversation to read

    Returns:
        The OpenHands server's response, passed through as-is
    """
    _require_plugin_auth(authorization)
    client = get_openhands_client()
    if not client.enabled:
        raise _plugin_unavailable("OpenHands", "Set OPENHANDS_API_URL.")
    result = client.get_conversation(conversation_id)
    if result is None:
        raise HTTPException(status_code=502, detail="OpenHands request failed")
    return result


@app.post("/api/voice-chat")
async def voice_chat(audio: UploadFile = File(...)):
    """
    Voice-based chat endpoint.
    Accepts audio input, transcribes it, generates response, and returns audio.

    Args:
        audio: Audio file (webm, mp3, wav, etc.)

    Returns:
        JSON with transcription, response text, and URL to audio response
    """
    try:
        # Save uploaded audio temporarily
        audio_id = str(uuid.uuid4())
        input_path = TEMP_DIR / f"input_{audio_id}.webm"

        with open(input_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        logger.info(f"Received audio file: {input_path}")

        # Transcribe audio to text
        vp = get_voice_processor_instance()
        transcription = await vp.transcribe_audio(input_path)
        logger.info(f"Transcription: {transcription}")

        # Get response from conductor
        result = get_conductor().chat(query=transcription)
        response_text = result['response']

        # Synthesize speech from response
        output_path = TEMP_DIR / f"output_{audio_id}.mp3"
        await vp.synthesize_speech(
            text=response_text,
            output_path=output_path,
            voice=current_voice_settings.voice
        )

        # Clean up input file
        input_path.unlink()

        return {
            "transcription": transcription,
            "response": response_text,
            "sources": result['sources'],
            "audio_url": f"/api/audio/{output_path.name}"
        }

    except Exception as e:
        logger.error(f"Error in voice chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    """
    Serve generated audio file.

    Args:
        filename: Name of audio file

    Returns:
        Audio file
    """
    file_path = TEMP_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        filename=filename
    )


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribe audio to text only.

    Args:
        audio: Audio file

    Returns:
        Transcribed text
    """
    try:
        # Save temporarily
        audio_id = str(uuid.uuid4())
        temp_path = TEMP_DIR / f"temp_{audio_id}.webm"

        with open(temp_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        # Transcribe
        transcription = await get_voice_processor_instance().transcribe_audio(temp_path)

        # Clean up
        temp_path.unlink()

        return {"transcription": transcription}

    except Exception as e:
        logger.error(f"Error in transcribe endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/synthesize")
async def synthesize(text: str, voice: Optional[str] = None):
    """
    Synthesize speech from text.

    Args:
        text: Text to convert to speech
        voice: Optional voice to use

    Returns:
        URL to audio file
    """
    try:
        audio_id = str(uuid.uuid4())
        output_path = TEMP_DIR / f"synth_{audio_id}.mp3"

        await get_voice_processor_instance().synthesize_speech(
            text=text,
            output_path=output_path,
            voice=voice or current_voice_settings.voice
        )

        return {"audio_url": f"/api/audio/{output_path.name}"}

    except Exception as e:
        logger.error(f"Error in synthesize endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/voices")
async def get_voices():
    """Get available TTS voices."""
    return {"voices": get_voice_processor_instance().get_available_voices()}


@app.post("/api/settings/voice")
async def set_voice(settings: VoiceSettings):
    """Update voice settings."""
    current_voice_settings.voice = settings.voice
    return {"voice": current_voice_settings.voice}


@app.get("/api/settings/voice")
async def get_voice_settings():
    """Get current voice settings."""
    return {"voice": current_voice_settings.voice}


# ---------------------------------------------------------------------------
# OpenAI-compatible API
#
# Lets any OpenAI-compatible client — TypingMind, LibreChat, the openai SDK,
# an IDE plugin — talk to the conductor by pointing its "custom model" base
# URL at this server. Only the fields the conductor can honor are read;
# everything else in the request is accepted and ignored so strict clients
# don't break.
# ---------------------------------------------------------------------------

CONDUCTOR_MODEL_ID = "conductor"

# Cap on the transcript rebuilt from a client's message history, in
# characters. Clients resend the whole conversation each turn, so without a
# bound a long chat would grow the prompt (and the bill) without limit.
MAX_TRANSCRIPT_CHARS = 12_000


def _require_conductor_key(authorization: Optional[str]) -> None:
    """Enforce CONDUCTOR_API_KEY on the OpenAI-compatible endpoints.

    Unset means open, matching /api/chat. Set it whenever this server is
    reachable from the internet: these endpoints spend your LLM credits.
    """
    expected = settings.conductor_key()
    if not expected:
        return
    presented = ""
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _flatten_messages(messages: List[ChatMessage]) -> str:
    """Turn a client's message list into a single query for the conductor.

    The conductor's chat() takes one string, so earlier turns are replayed
    as a labelled transcript above the latest user message. The transcript
    is trimmed from the front — recent turns matter most — and the final
    user message is always kept whole.
    """
    if not messages:
        return ""

    last = messages[-1]
    query = last.content.strip()
    earlier = messages[:-1]
    if not earlier:
        return query

    lines = [f"{m.role}: {m.content.strip()}" for m in earlier if m.content.strip()]
    transcript = "\n".join(lines)
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = "...\n" + transcript[-MAX_TRANSCRIPT_CHARS:]
    if not transcript:
        return query
    return f"Conversation so far:\n{transcript}\n\nLatest message:\n{query}"


def _completion_payload(text: str, model: str, completion_id: str) -> Dict[str, Any]:
    """Build a non-streaming chat-completion response body."""
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        # Token accounting isn't tracked across the providers the conductor
        # fronts; zeros keep the shape valid for clients that read it.
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _sse_chunk(
    completion_id: str,
    model: str,
    created: int,
    delta: Dict[str, Any],
    finish_reason: Optional[str] = None,
) -> str:
    """Render one OpenAI-style chat.completion.chunk SSE event."""
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _stream_completion(generate, model: str, completion_id: str):
    """Stream a completion, generating only after the response has opened.

    `generate` is called *inside* the iterator, after the opening role
    chunk has been flushed, so the client and any proxy in between see
    headers and a first event immediately instead of waiting out the whole
    provider call on a silent socket. The conductor's chat() is
    synchronous, so the answer still arrives in one piece and the
    subsequent chunks pace it out; what this buys is the open connection,
    not token-by-token generation.

    A failure after the stream has opened can't become an HTTP error code
    any more, so it is delivered as a final content chunk instead.
    """
    created = int(time.time())
    yield _sse_chunk(completion_id, model, created, {"role": "assistant", "content": ""})

    try:
        text = generate()
    except Exception as e:
        logger.error(f"Error generating streamed completion: {e}")
        yield _sse_chunk(
            completion_id,
            model,
            created,
            {"content": f"\n\n[error: {type(e).__name__}: {e}]"},
        )
        yield _sse_chunk(completion_id, model, created, {}, finish_reason="stop")
        yield "data: [DONE]\n\n"
        return

    for i in range(0, len(text), 120):
        yield _sse_chunk(completion_id, model, created, {"content": text[i : i + 120]})
    yield _sse_chunk(completion_id, model, created, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


@app.get("/v1/models")
async def list_models(authorization: Optional[str] = Header(default=None)):
    """List the models this server exposes (one: the conductor itself)."""
    _require_conductor_key(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": CONDUCTOR_MODEL_ID,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "conductor",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: Optional[str] = Header(default=None),
):
    """
    OpenAI-compatible chat completions, answered by the conductor.

    Args:
        request: An OpenAI chat-completions request; `messages` and
            `stream` are honored, sampling parameters are ignored
        authorization: Bearer token, required when CONDUCTOR_API_KEY is set

    Returns:
        A chat.completion body, or an SSE stream of chat.completion.chunk
        events when `stream` is true
    """
    _require_conductor_key(authorization)

    query = _flatten_messages(request.messages)
    if not query:
        raise HTTPException(status_code=400, detail="messages must contain content")

    # Only the newest message drives Firecrawl's auto-fetch. The flattened
    # query carries the whole history, and URLs from turns already answered
    # would otherwise be re-scraped every turn — burning credits and
    # crowding out the link actually being asked about.
    latest = request.messages[-1].content.strip()

    # The response is always labelled with the model this server actually
    # serves, never the id the client asked for: the conductor routes to
    # whichever provider is configured, so echoing "gpt-4" back would
    # misattribute a Claude or Gemini answer in the caller's logs.
    model = CONDUCTOR_MODEL_ID
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"

    def generate() -> str:
        # request.user scopes durable memory per client-supplied end user;
        # None falls back to the shared default (see MEM0_DEFAULT_USER_ID).
        return get_conductor().chat(
            query=query, user_id=request.user, url_source=latest
        )["response"]

    if request.stream:
        return StreamingResponse(
            _stream_completion(generate, model, completion_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        text = generate()
    except Exception as e:
        logger.error(f"Error in chat completions endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return _completion_payload(text, model, completion_id)


# Mount static files (will create later)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))

    logger.info(f"Starting Conductor Voice Agent on port {port}")

    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
