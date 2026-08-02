"""
Minimal, dependency-light conductor used in cloud or fallback mode.
Calls whichever LLM provider has a key set (AWS Bedrock Claude,
Google/Gemini, OpenAI, Anthropic, or xAI/Grok). No ChromaDB, no heavy
local deps.
"""
import json
import os
from typing import Dict, Any, Iterator
from config.settings import settings
from conductor.memory import Mem0Memory
from utils.logger import logger


def _provider_for_keys() -> tuple:
    """Pick (provider, model) based on which env var is set."""
    if settings.bedrock_configured():
        return "bedrock", settings.bedrock_model()
    if os.getenv("GOOGLE_API_KEY"):
        return "google", "gemini-1.5-flash"
    if os.getenv("OPENAI_API_KEY", "").startswith("sk-"):
        return "openai", "gpt-4o-mini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic", "claude-3-5-haiku-latest"
    if os.getenv("XAI_API_KEY"):
        return "xai", "grok-2-latest"
    return "none", "minimal"


class MinimalConductor:
    """Cloud-safe conductor. Calls whichever AI provider is configured."""

    def __init__(self):
        self.retriever = None
        self.current_skill = None
        self.skill_manager = None
        self.provider, self.model = _provider_for_keys()
        self.memory = Mem0Memory()
        logger.info(
            f"MinimalConductor initialized (provider={self.provider}, "
            f"model={self.model}, memory={'on' if self.memory.enabled else 'off'})"
        )

    def activate_skill(self, skill_name: str) -> bool:
        return False

    def _system_prompt(self) -> str:
        return "You are Conductor, a helpful voice AI assistant. Be concise and conversational."

    def _call_google(self, query: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        model = genai.GenerativeModel(self.model, system_instruction=self._system_prompt())
        resp = model.generate_content(query)
        return resp.text or ""

    def _call_bedrock(self, query: str) -> str:
        import boto3

        client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region())
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": self._system_prompt(),
            "messages": [{"role": "user", "content": query}],
        }
        resp = client.invoke_model(
            modelId=self.model,
            body=json.dumps(payload),
            accept="application/json",
            contentType="application/json",
        )
        data = json.loads(resp["body"].read())
        return "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )

    def _call_openai(self, query: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": query},
            ],
        )
        return resp.choices[0].message.content or ""

    def _call_anthropic(self, query: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self._system_prompt(),
            messages=[{"role": "user", "content": query}],
        )
        return "".join(block.text for block in resp.content if hasattr(block, "text"))

    def _call_xai(self, query: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1")
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": query},
            ],
        )
        return resp.choices[0].message.content or ""

    def chat(
        self, query: str, platform_filter: str = None, user_id: str = None
    ) -> Dict[str, Any]:
        # Search shared memory before replying, then fold it into the prompt.
        memory_context = self.memory.search(query, user_id=user_id)
        augmented = query
        if memory_context:
            augmented = (
                "What you already know about this caller/user:\n"
                f"{memory_context}\n\n"
                f"Current message: {query}"
            )
        succeeded = True
        try:
            if self.provider == "bedrock":
                text = self._call_bedrock(augmented)
            elif self.provider == "google":
                text = self._call_google(augmented)
            elif self.provider == "openai":
                text = self._call_openai(augmented)
            elif self.provider == "anthropic":
                text = self._call_anthropic(augmented)
            elif self.provider == "xai":
                text = self._call_xai(augmented)
            else:
                succeeded = False
                text = (
                    "Minimal mode: no AI provider configured. "
                    "Set AWS_REGION (for Bedrock Claude), OPENAI_API_KEY, "
                    "GOOGLE_API_KEY, ANTHROPIC_API_KEY or XAI_API_KEY."
                )
        except Exception as e:
            succeeded = False
            logger.error(f"MinimalConductor provider call failed ({self.provider}): {e}")
            text = f"Sorry — the {self.provider} provider failed: {type(e).__name__}: {e}"

        # Only persist real replies; never write error/fallback strings into
        # shared memory, or they pollute future prompts.
        if succeeded:
            self.memory.add(query, text, user_id=user_id)

        return {
            "response": text,
            "sources": [],
            "context_used": 1 if memory_context else 0,
            "model": f"{self.provider}:{self.model}",
            "memory": self.memory.enabled,
        }

    def stream_chat(self, query: str, platform_filter: str = None) -> Iterator[Dict[str, Any]]:
        yield {"type": "sources", "data": []}
        resp = self.chat(query, platform_filter=platform_filter)["response"]
        chunk_size = 120
        for i in range(0, len(resp), chunk_size):
            yield {"type": "content", "data": resp[i : i + chunk_size]}
