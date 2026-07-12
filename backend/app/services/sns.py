"""SNS content generation / draft publishing for market commentary."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import SnsPost


class SnsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    def draft_market_comment(
        self,
        ticker: str,
        direction: str,
        confidence: float,
        predicted_price: float,
    ) -> str:
        arrow = "上昇" if direction == "up" else "下落"
        return (
            f"【AI相場メモ】{ticker}\n"
            f"予測方向: {arrow} / 信頼度 {confidence:.0%}\n"
            f"想定価格: {predicted_price:,.2f}\n"
            f"※投資判断は自己責任で。これは自動生成の研究コメントです。"
        )

    async def create_draft(
        self,
        ticker: str,
        direction: str,
        confidence: float,
        predicted_price: float,
        auto_publish: bool = False,
    ) -> SnsPost:
        content = self.draft_market_comment(ticker, direction, confidence, predicted_price)
        post = SnsPost(
            platform="x",
            content=content,
            status="draft",
            related_symbol=ticker,
        )
        if auto_publish and self.settings.x_bearer_token:
            # Live publish hook — intentionally gated; implement X API v2 when credentials set
            post.status = "queued"
            post.scheduled_at = datetime.now(timezone.utc)
        self.db.add(post)
        await self.db.commit()
        await self.db.refresh(post)
        return post
