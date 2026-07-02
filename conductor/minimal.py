"""
Minimal, dependency-light conductor fallback used in cloud or when no
AI provider is configured. This provides the same public methods the full
`ConductorAgent` exposes (`chat`, `stream_chat`, `activate_skill`) but
does not rely on heavy dependencies like ChromaDB or external SDKs.

The goal is to allow the API/CLI to start and return helpful messages
when running in constrained environments.
"""
from pathlib import Path
from typing import Dict, Any, Iterator
from skills.manager import SkillManager
from utils.logger import logger
from config import settings


class MinimalConductor:
    """Very small conductor implementation for fallbacks and tests."""

    def __init__(self):
        # Only load skills metadata (no execution runtime required)
        skills_path = Path(__file__).resolve().parent.parent / "skills"
        try:
            self.skill_manager = SkillManager(skills_path)
        except Exception:
            self.skill_manager = None

        self.retriever = None
        self.current_skill = None
        self.model = "minimal"

        logger.info("Initialized MinimalConductor (no external AI providers)")

    def activate_skill(self, skill_name: str) -> bool:
        """Activate a skill if available. Returns True on success."""
        if not self.skill_manager:
            return False

        skill = self.skill_manager.get_skill(skill_name)
        if skill:
            self.current_skill = skill
            logger.info(f"Activated skill (minimal): {skill.name}")
            return True
        return False

    def chat(self, query: str, platform_filter: str = None) -> Dict[str, Any]:
        """Return a short, helpful response explaining minimal mode."""
        base = (
            "Minimal mode: no AI provider configured. "
            "Set OPENAI_API_KEY, GOOGLE_API_KEY or XAI_API_KEY to enable full-mode."
        )

        if self.current_skill:
            # Include skill's brief guidance if a skill is active
            try:
                skill_hint = f"\n\nSkill: {self.current_skill.name} - {self.current_skill.description}"
            except Exception:
                skill_hint = ""
        else:
            skill_hint = ""

        return {
            "response": f"{base}{skill_hint}\n\n(You asked: {query})",
            "sources": [],
            "context_used": 0,
            "model": self.model,
        }

    def stream_chat(self, query: str, platform_filter: str = None) -> Iterator[Dict[str, Any]]:
        """Yield a minimal stream: first empty sources, then the response in chunks."""
        # Yield empty sources list first for parity with full conductor
        yield {"type": "sources", "data": []}

        resp = self.chat(query, platform_filter=platform_filter)["response"]

        # Stream in small chunks
        chunk_size = 120
        for i in range(0, len(resp), chunk_size):
            yield {"type": "content", "data": resp[i : i + chunk_size]}

        return
