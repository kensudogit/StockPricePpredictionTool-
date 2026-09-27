/** Turn profit-gate text into a Japanese hold notice (not a crash). */

export function isGateHoldMessage(text: string): boolean {
  return /見送り|expected_value|short_ev|hit_z|oos_sharpe|oos_strategy|momentum|min_hit|関門|期待値|モメンタム|確認窓|検証/.test(
    text,
  );
}

export function formatBlockReason(raw: string | null | undefined): string {
  if (!raw) return "関門未通過";
  return raw
    .split(";")
    .map((part) => translateClause(part.trim()))
    .filter(Boolean)
    .join("。");
}

function translateClause(s: string): string {
  if (!s) return "";
  if (/[\u3000-\u9fff]/.test(s) && !/expected_value|short_ev|hit_z|oos_/.test(s)) {
    return s;
  }
  const ev = s.match(/min\(short_ev,long_ev\)\s*=?\s*(-?[\d.]+)\s*<\s*(-?[\d.]+)/i);
  if (ev) {
    return `期待値 ${(Number(ev[1]) * 10000).toFixed(1)}bps が下限 ${(Number(ev[2]) * 10000).toFixed(1)}bps 未満`;
  }
  const ev2 = s.match(/expected_value\s+(-?[\d.]+)\s*<\s*(-?[\d.]+)/i);
  if (ev2) {
    return `期待値 ${(Number(ev2[1]) * 10000).toFixed(1)}bps が下限 ${(Number(ev2[2]) * 10000).toFixed(1)}bps 未満`;
  }
  if (/long oos_strategy_return/i.test(s)) return "確認窓の手数料後リターンがマイナス";
  if (/oos_strategy_return/i.test(s)) return "検証リターンがマイナス";
  const z = s.match(/hit_z\s+(-?[\d.]+)\s*<\s*(-?[\d.]+)/i);
  if (z) return `的中の信頼度 z=${Number(z[1]).toFixed(2)} が不足`;
  const sh = s.match(/oos_sharpe\s+(-?[\d.]+)\s*<\s*(-?[\d.]+)/i);
  if (sh) return `Sharpe ${Number(sh[1]).toFixed(2)} が下限未満`;
  if (/20d momentum not up/i.test(s)) return "20日モメンタムが上向きでない";
  if (/20d momentum not down/i.test(s)) return "20日モメンタムが下向きでない";
  if (/counter-trend long/i.test(s)) return "株価トレンドと逆の買い";
  if (/counter-trend short/i.test(s)) return "株価トレンドと逆の売り";
  if (/index downtrend/i.test(s)) return "日経平均が下降中のため買い見送り";
  if (/index uptrend/i.test(s)) return "日経平均が上昇中のため売り見送り";
  if (/qty below lot/i.test(s)) return "数量が東証単元に満たない";
  return s;
}
