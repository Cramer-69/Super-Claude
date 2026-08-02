"""
Configuration management for Conductor Agent.
Loads settings from environment variables and .env file.
"""

import os
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional


def _real_key(value: Optional[str]) -> Optional[str]:
    """Return `value` unless it's blank or a `.env.example` placeholder.

    Whitespace is stripped first, so a key that's only spaces (easy to end
    up with from a shell export or a copy-pasted .env line) reads as unset
    rather than marking a provider or plugin configured.
    """
    if not value:
        return None
    stripped = value.strip()
    if not stripped or stripped.startswith("your_"):
        return None
    return stripped


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # LLM API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    perplexity_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None
    aws_region: Optional[str] = None
    aws_bedrock_model_id: Optional[str] = None

    # Durable cross-session memory (mem0). Off by default: requires the
    # optional `mem0ai` package and either a MEM0_API_KEY (hosted mem0
    # platform) or, for the self-hosted/OSS backend, an OpenAI key for
    # mem0's own LLM/embedder calls. Setting MEM0_API_KEY is itself an
    # opt-in, so MEM0_ENABLED is only needed for the OSS backend.
    mem0_enabled: bool = False
    mem0_api_key: Optional[str] = None
    mem0_default_user_id: str = "default"

    # Web reading via Firecrawl (https://firecrawl.dev). Off by default:
    # requires the optional `firecrawl-py` package plus a FIRECRAWL_API_KEY
    # (or FIRECRAWL_API_URL pointing at a self-hosted instance).
    firecrawl_api_key: Optional[str] = None
    firecrawl_api_url: Optional[str] = None
    # Per-page cap on scraped text handed to a model, in characters.
    firecrawl_max_content_chars: int = 4000
    # Auto-read URLs the user mentions in a chat query.
    firecrawl_auto_fetch_urls: bool = True
    firecrawl_max_urls_per_query: int = 2
    # Allow fetching loopback/private/link-local hosts. Off by default: a
    # self-hosted Firecrawl sits inside your network, so an attacker-supplied
    # URL would otherwise reach internal services. Turn on only when you
    # deliberately crawl an internal site.
    firecrawl_allow_private_hosts: bool = False

    # Realtime voice rooms via LiveKit. Off until all three are set.
    livekit_url: Optional[str] = None
    livekit_api_key: Optional[str] = None
    livekit_api_secret: Optional[str] = None
    livekit_token_ttl_seconds: int = 3600

    # Dify app backend (https://dify.ai). Off until an app key is set.
    dify_api_key: Optional[str] = None
    dify_api_url: str = "https://api.dify.ai/v1"

    # OpenHands agent runtime. Off until its base URL is set.
    openhands_api_url: Optional[str] = None
    openhands_api_key: Optional[str] = None

    # Shared HTTP timeout for the plugin clients above, in seconds.
    plugin_http_timeout: float = 30.0

    # Optional bearer token guarding the OpenAI-compatible endpoints.
    # Unset means unauthenticated, matching /api/chat.
    conductor_api_key: Optional[str] = None

    # Model Configuration
    conductor_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    
    # Vector Database
    chroma_persist_dir: str = "./data/chroma_db"
    conversations_collection: str = "conversations"
    code_collection: str = "code_snippets"
    decisions_collection: str = "decisions"
    solutions_collection: str = "solutions"
    
    # Data Processing
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 5
    
    # API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    debug: bool = False

    # Data Paths
    raw_data_dir: str = "./data/raw"
    processed_data_dir: str = "./data/processed"
    # Leave blank by default; users opt in by setting ANTIGRAVITY_BRAIN_DIR.
    antigravity_brain_dir: str = ""
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/conductor.log"
    
    def get_base_path(self) -> Path:
        """Get the base path of the conductor_agent directory."""
        return Path(__file__).parent.parent
    
    def get_chroma_path(self) -> Path:
        """Get absolute path to ChromaDB persistence directory."""
        base = self.get_base_path()
        return base / self.chroma_persist_dir
    
    def get_raw_data_path(self) -> Path:
        """Get absolute path to raw data directory."""
        base = self.get_base_path()
        return base / self.raw_data_dir
    
    def get_processed_data_path(self) -> Path:
        """Get absolute path to processed data directory."""
        base = self.get_base_path()
        return base / self.processed_data_dir
    
    def validate_api_keys(self) -> bool:
        """Check if at least one LLM API key is configured."""
        return any([
            self.bedrock_configured(),
            self.openai_api_key,
            self.anthropic_api_key,
            self.google_api_key
        ])

    def bedrock_region(self) -> Optional[str]:
        """Return configured AWS Bedrock region, honoring AWS defaults."""
        return (
            os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or self.aws_region
        )

    def bedrock_model(self) -> str:
        """Return configured AWS Bedrock Claude model."""
        return (
            os.getenv("AWS_BEDROCK_MODEL_ID")
            or self.aws_bedrock_model_id
            or "anthropic.claude-3-5-haiku-20241022-v1:0"
        )

    def bedrock_configured(self) -> bool:
        """Check whether AWS Bedrock Claude is configured."""
        return bool(self.bedrock_region())

    def mem0_platform_key(self) -> Optional[str]:
        """Return the hosted mem0 platform key, or None if unset/placeholder."""
        return _real_key(self.mem0_api_key)

    def mem0_configured(self) -> bool:
        """Check whether durable memory is opted into.

        A hosted platform key counts as an opt-in on its own; the OSS
        backend needs the explicit MEM0_ENABLED flag because it silently
        spends OpenAI credits on mem0's own LLM/embedder calls.
        """
        return bool(self.mem0_enabled or self.mem0_platform_key())

    def firecrawl_key(self) -> Optional[str]:
        """Return the Firecrawl API key, or None if unset/placeholder."""
        return _real_key(self.firecrawl_api_key)

    def firecrawl_configured(self) -> bool:
        """Check whether Firecrawl is opted into.

        A self-hosted instance (FIRECRAWL_API_URL) may not need a key, so
        either setting is enough.
        """
        return bool(self.firecrawl_key() or self.firecrawl_api_url)

    def livekit_credentials(self) -> Optional[tuple[str, str, str]]:
        """Return (url, api_key, api_secret), or None if any is missing."""
        url = _real_key(self.livekit_url)
        key = _real_key(self.livekit_api_key)
        secret = _real_key(self.livekit_api_secret)
        if url and key and secret:
            return url, key, secret
        return None

    def livekit_configured(self) -> bool:
        return self.livekit_credentials() is not None

    def dify_key(self) -> Optional[str]:
        return _real_key(self.dify_api_key)

    def dify_configured(self) -> bool:
        return bool(self.dify_key())

    def openhands_base_url(self) -> Optional[str]:
        return _real_key(self.openhands_api_url)

    def openhands_configured(self) -> bool:
        return bool(self.openhands_base_url())

    def conductor_key(self) -> Optional[str]:
        """Bearer token required by the OpenAI-compatible API, if any."""
        return _real_key(self.conductor_api_key)

    def configured_providers(self) -> list[str]:
        """Return names of providers with a non-placeholder key set."""
        candidates = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
            "xai": self.xai_api_key,
            "perplexity": self.perplexity_api_key,
        }
        providers = [name for name, key in candidates.items() if _real_key(key)]
        if self.bedrock_configured():
            providers.insert(0, "bedrock")
        return providers

    def require_api_key(self) -> None:
        """Fail fast at startup with an actionable error if no key is set."""
        if self.configured_providers():
            return
        raise RuntimeError(
            "No LLM API key is configured.\n"
            "  - Bedrock:   set AWS_REGION (and optionally AWS_BEDROCK_MODEL_ID)\n"
            "  - Local:     copy .env.example -> .env and set OPENAI_API_KEY=sk-...\n"
            "  - Docker:    docker run -e OPENAI_API_KEY=sk-... -p 8080:8080 <image>\n"
            "  - Cloud Run: gcloud run deploy --set-secrets "
            "OPENAI_API_KEY=openai-api-key:latest\n"
            "See README.md -> Deploy."
        )


# Global settings instance
settings = Settings()


# Ensure required directories exist
def init_directories():
    """Create necessary directories if they don't exist."""
    base = settings.get_base_path()
    
    dirs_to_create = [
        base / "data",
        base / "data" / "raw",
        base / "data" / "processed",
        base / "data" / "chroma_db",
        base / "logs",
    ]
    
    for dir_path in dirs_to_create:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # Read-only filesystem (e.g. Vercel/serverless, where only /tmp
            # is writable). config.settings is imported very early — by
            # nearly every module, including the logger — so raising here
            # would crash the whole app before it can even fall back.
            print(
                f"[settings] could not create directory {dir_path}: {exc}; "
                "continuing without it",
                file=sys.stderr,
            )


# Initialize on import
init_directories()
