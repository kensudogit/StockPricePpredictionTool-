"""Pure scoring helpers for integrated analysis (no DB imports)."""

from __future__ import annotations

from typing import Any


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def np_mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def score_technical(snap: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    parts: list[float] = []

    trend = str(snap.get("trend") or "unknown")
    if "up" in trend:
        parts.append(0.45)
        reasons.append(f"トレンド: {trend}（強気寄り）")
    elif "down" in trend:
        parts.append(-0.45)
        reasons.append(f"トレンド: {trend}（弱気寄り）")
    else:
        parts.append(0.0)
        reasons.append(f"トレンド: {trend}")

    rsi = snap.get("rsi_14")
    if rsi is not None:
        rsi_f = float(rsi)
        if rsi_f >= 70:
            parts.append(-0.35)
            reasons.append(f"RSI {rsi_f:.1f}: 過熱（反落リスク）")
        elif rsi_f <= 30:
            parts.append(0.35)
            reasons.append(f"RSI {rsi_f:.1f}: 売られ過ぎ（反発余地）")
        else:
            mid = (rsi_f - 50) / 50.0 * 0.2
            parts.append(mid)
            reasons.append(f"RSI {rsi_f:.1f}: 中立帯")

    macd = snap.get("macd")
    macd_sig = snap.get("macd_signal")
    if macd is not None and macd_sig is not None:
        hist = float(macd) - float(macd_sig)
        parts.append(_clip(hist / (abs(float(macd_sig)) + 1e-6) * 0.25, -0.35, 0.35))
        reasons.append(f"MACDヒスト {'+' if hist >= 0 else ''}{hist:.3f}")

    adx = snap.get("adx")
    if adx is not None and float(adx) >= 25:
        bias = 0.15 if parts and parts[0] > 0 else (-0.15 if parts and parts[0] < 0 else 0.0)
        parts.append(bias)
        reasons.append(f"ADX {float(adx):.1f}: トレンド強度あり")

    score = _clip(float(np_mean(parts)) if parts else 0.0)
    return score, reasons


def score_fundamentals(fund: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not fund:
        return 0.0, ["ファンダメンタル未取得"]
    reasons: list[str] = []
    parts: list[float] = []

    per = fund.get("per")
    if per is not None and float(per) > 0:
        per_f = float(per)
        if per_f < 12:
            parts.append(0.35)
            reasons.append(f"PER {per_f:.1f}: 割安寄り")
        elif per_f > 25:
            parts.append(-0.3)
            reasons.append(f"PER {per_f:.1f}: 割高寄り")
        else:
            parts.append(0.05)
            reasons.append(f"PER {per_f:.1f}: 適正帯")

    pbr = fund.get("pbr")
    if pbr is not None and float(pbr) > 0:
        pbr_f = float(pbr)
        if pbr_f < 1.0:
            parts.append(0.25)
            reasons.append(f"PBR {pbr_f:.2f}: 純資産割れ寄り")
        elif pbr_f > 3.0:
            parts.append(-0.2)
            reasons.append(f"PBR {pbr_f:.2f}: プレミアム高い")
        else:
            parts.append(0.05)
            reasons.append(f"PBR {pbr_f:.2f}")

    roe = fund.get("roe")
    if roe is not None:
        roe_f = float(roe)
        if roe_f >= 0.12:
            parts.append(0.3)
            reasons.append(f"ROE {roe_f * 100:.1f}%: 収益性良好")
        elif roe_f < 0.05:
            parts.append(-0.25)
            reasons.append(f"ROE {roe_f * 100:.1f}%: 収益性低め")
        else:
            parts.append(0.05)
            reasons.append(f"ROE {roe_f * 100:.1f}%")

    om = fund.get("operating_margin")
    if om is not None:
        om_f = float(om)
        parts.append(_clip(om_f * 2.0, -0.25, 0.3))
        reasons.append(f"営業利益率 {om_f * 100:.1f}%")

    if not parts:
        return 0.0, ["ファンダ指標が不足"]
    return _clip(np_mean(parts)), reasons


def score_news(articles: list[dict[str, Any]]) -> tuple[float, list[str], dict[str, Any]]:
    if not articles:
        return 0.0, ["関連ニュースなし（収集を実行）"], {"count": 0, "avg_sentiment": None, "labels": {}}

    scores = [float(a["sentiment"]) for a in articles if a.get("sentiment") is not None]
    labels: dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0}
    for a in articles:
        lab = (a.get("sentiment_label") or "neutral").lower()
        if lab not in labels:
            lab = "neutral"
        labels[lab] += 1

    avg = float(np_mean(scores)) if scores else 0.0
    score = _clip(avg)
    reasons = [
        f"ニュース {len(articles)} 件 · 平均センチメント {avg:+.2f}",
        f"内訳 ポジ {labels['positive']} / 中立 {labels['neutral']} / ネガ {labels['negative']}",
    ]
    for a in articles[:3]:
        lab = a.get("sentiment_label") or "—"
        reasons.append(f"[{lab}] {str(a.get('title') or '')[:60]}")

    return score, reasons, {"count": len(articles), "avg_sentiment": avg, "labels": labels}


def combine_scores(
    technical: float,
    fundamental: float,
    news: float,
    *,
    weights: tuple[float, float, float] = (0.45, 0.30, 0.25),
) -> tuple[float, str, float]:
    w_t, w_f, w_n = weights
    composite = _clip(w_t * technical + w_f * fundamental + w_n * news)
    strength = abs(composite)
    if composite >= 0.25:
        signal = "buy"
    elif composite <= -0.25:
        signal = "sell"
    else:
        signal = "hold"
    return composite, signal, strength
