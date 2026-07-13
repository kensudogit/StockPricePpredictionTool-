"""Investment chat assistant: answers why-buy / risk using insight + RAG context."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.clients import NewsLLMService
from app.models import ChatMessage, Position, RiskEvent, Symbol
from app.rag.store import RAGService
from app.services.insight import InsightService


def _detect_intent(question: str) -> str:
    q = question.lower()
    if any(k in question for k in ("なぜ買", "買い理由", "なぜ買い", "根拠", "why buy", "why")):
        return "why_buy"
    if any(k in question for k in ("なぜ売", "売り理由", "なぜ売り")):
        return "why_sell"
    if any(k in question for k in ("リスク", "危険", "下落", "損", "risk", "drawdown")):
        return "risk"
    if any(k in question for k in ("要約", "ニュース", "相場")):
        return "news"
    if any(k in q for k in ("backtest", "バックテスト", "勝率", "精度")):
        return "backtest"
    return "general"


def _system_prompt(intent: str) -> str:
    base = (
        "あなたは日本語の投資アシスタントです。"
        "与えられたコンテキストのみを根拠に、簡潔・具体的に答えてください。"
        "投資助言の断定は避け、不確実性を明示してください。"
        "コンテキストに無い事実は作らないでください。"
    )
    extra = {
        "why_buy": "買い根拠（シグナル・XAI寄与・ニュース）を優先して説明。",
        "why_sell": "売り根拠を優先して説明。",
        "risk": "最大DD・信頼度・ネガティブ要因・ポジションリスクを列挙。",
        "news": "ニュース要約とセンチメントを中心に。",
        "backtest": "勝率・リターン・DDなどバックテスト指標を中心に。",
        "general": "質問に直接答え、必要ならシグナルとリスクを短く添える。",
    }
    return base + extra.get(intent, extra["general"])


def _format_insight_context(insight: dict[str, Any]) -> str:
    price = insight.get("price") or {}
    conf = insight.get("confidence") or {}
    signal = insight.get("signal") or {}
    news = insight.get("news") or {}
    bt = (insight.get("backtest") or {}).get("metrics") or {}
    acc = insight.get("accuracy") or {}
    expl = insight.get("explanation") or {}
    feats = (expl.get("features") or [])[:5]
    feat_lines = "\n".join(
        f"  - {f.get('label')}: impact={f.get('impact'):+.4f} value={f.get('value')}"
        for f in feats
    )
    return f"""
銘柄: {insight.get('ticker')}
最終終値: {price.get('last_close')}
予測価格: {price.get('predicted_price')} ({price.get('predicted_return')})
方向: {price.get('direction')}
信頼度: {conf.get('value')} ({conf.get('label')})
シグナル: {signal.get('label')} / {signal.get('action')} (source={signal.get('source')})
XAI手法: {expl.get('method')}
主要寄与:
{feat_lines}
ニュース要約: {news.get('summary')}
バックテスト勝率: {bt.get('win_rate')} / リターン: {bt.get('total_return')} / MaxDD: {bt.get('max_drawdown')} / Sharpe: {bt.get('sharpe')}
Walk-forward的中率: {acc.get('direction_hit_rate')} (n={acc.get('n_samples')})
統合: {insight.get('integrated')}
""".strip()


class ChatAssistantService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ask(
        self,
        *,
        ticker: str,
        question: str,
        session_id: str = "web",
        intent: str | None = None,
        insight: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        intent = intent or _detect_intent(question)
        if not insight or not insight.get("ok"):
            insight = await InsightService(self.db).build(
                ticker, collect_news=True, run_backtest=True, persist_prediction=False
            )

        rag = RAGService(self.db)
        try:
            rag_res = await rag.query(f"{ticker} {question}", limit=5)
        except Exception as e:  # noqa: BLE001
            rag_res = {"hits": [], "context": "", "warning": str(e)}

        # Position / risk snippets
        pos_txt = ""
        sym = (await self.db.execute(select(Symbol).where(Symbol.ticker == ticker))).scalar_one_or_none()
        if sym:
            pos = (
                await self.db.execute(select(Position).where(Position.symbol_id == sym.id))
            ).scalar_one_or_none()
            if pos:
                pos_txt = f"保有数量={pos.quantity} 平均取得={pos.avg_cost}"
        risks = (
            await self.db.execute(select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(3))
        ).scalars().all()
        risk_txt = "\n".join(f"- [{r.severity}] {r.event_type}: {r.message}" for r in risks)

        history = (
            await self.db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(8)
            )
        ).scalars().all()
        hist_txt = "\n".join(
            f"{m.role}: {m.content[:400]}" for m in reversed(list(history))
        )

        user_blob = f"""質問: {question}
意図: {intent}

【インサイト】
{_format_insight_context(insight) if insight.get('ok') else insight}

【ポジション】{pos_txt or 'なし'}
【直近リスクイベント】
{risk_txt or 'なし'}

【RAGコンテキスト】
{rag_res.get('context') or '(empty)'}

【会話履歴】
{hist_txt or '(empty)'}
"""
        answer = await NewsLLMService().llm.complete(_system_prompt(intent), user_blob)

        self.db.add(ChatMessage(session_id=session_id, role="user", content=question))
        self.db.add(ChatMessage(session_id=session_id, role="assistant", content=answer))
        await self.db.commit()

        # Optional: index Q&A for future retrieval
        try:
            await rag.ingest_text(
                content=f"Q: {question}\nA: {answer}",
                doc_type="chat",
                title=f"{ticker} chat",
                symbol_id=sym.id if sym else None,
                source_ref=session_id,
            )
        except Exception:  # noqa: BLE001
            pass

        return {
            "ticker": ticker,
            "question": question,
            "intent": intent,
            "answer": answer,
            "session_id": session_id,
            "hits": rag_res.get("hits") or [],
            "suggested": [
                "なぜ買い（または売り）なのか？",
                "主なリスクは？",
                "ニュース要約を教えて",
                "バックテストの勝率は？",
            ],
            "insight_snapshot": {
                "signal": insight.get("signal") if insight else None,
                "price": insight.get("price") if insight else None,
                "confidence": insight.get("confidence") if insight else None,
            },
        }
