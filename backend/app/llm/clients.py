"""LLM clients: OpenAI / Claude / Gemini with heuristic fallback."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from app.config import get_settings

Provider = Literal["openai", "claude", "gemini", "heuristic"]


class LLMClient:
    def __init__(self, provider: Provider | None = None) -> None:
        self.settings = get_settings()
        self.provider: Provider = provider or self._default_provider()

    def _default_provider(self) -> Provider:
        if self.settings.openai_api_key:
            return "openai"
        if self.settings.anthropic_api_key:
            return "claude"
        if self.settings.google_api_key:
            return "gemini"
        return "heuristic"

    async def complete(self, system: str, user: str, model: str | None = None) -> str:
        if self.provider == "openai":
            return await self._openai(system, user, model or self.settings.openai_model)
        if self.provider == "claude":
            return await self._claude(system, user, model or self.settings.anthropic_model)
        if self.provider == "gemini":
            return await self._gemini(system, user, model or self.settings.google_model)
        return self._heuristic(user)

    async def _openai(self, system: str, user: str, model: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def _claude(self, system: str, user: str, model: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    async def _gemini(self, system: str, user: str, model: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                params={"key": self.settings.google_api_key},
                json={"contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}]},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    def _heuristic(self, text: str) -> str:
        return f"[heuristic] {text[:500]}"


POSITIVE = ("上昇", "増益", "最高益", "上方修正", "好調", "beat", "surge", "growth", "record")
NEGATIVE = ("下落", "減益", "下方修正", "赤字", "低迷", "miss", "plunge", "lawsuit", "recall")


def heuristic_sentiment(text: str) -> dict[str, Any]:
    t = text.lower()
    pos = sum(1 for w in POSITIVE if w.lower() in t or w in text)
    neg = sum(1 for w in NEGATIVE if w.lower() in t or w in text)
    score = (pos - neg) / max(pos + neg, 1)
    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"
    return {"score": round(score, 4), "label": label, "provider": "heuristic"}


class NewsLLMService:
    """News summary / IR parse / earnings briefing / sentiment."""

    def __init__(self, provider: Provider | None = None) -> None:
        self.llm = LLMClient(provider)

    async def summarize(self, text: str) -> str:
        return await self.llm.complete(
            "あなたは金融アナリストです。ニュースを3文以内で要約してください。",
            text[:6000],
        )

    async def parse_ir(self, text: str) -> str:
        return await self.llm.complete(
            "IR/適時開示を解析し、重要ファクト・数値・今後の注目点を箇条書きで抽出してください。",
            text[:8000],
        )

    async def parse_earnings(self, text: str) -> str:
        return await self.llm.complete(
            "決算・決算説明会の内容から、売上/利益/ガイダンス/Q&Aの要点を整理してください。",
            text[:8000],
        )

    async def sentiment(self, text: str) -> dict[str, Any]:
        if self.llm.provider == "heuristic":
            return heuristic_sentiment(text)
        raw = await self.llm.complete(
            '金融テキストのセンチメントを JSON のみで返してください。形式: {"score": -1.0〜1.0, "label": "positive|neutral|negative"}',
            text[:4000],
        )
        import json
        import re

        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return heuristic_sentiment(text)
        try:
            data = json.loads(m.group())
            data["provider"] = self.llm.provider
            return data
        except json.JSONDecodeError:
            return heuristic_sentiment(text)
