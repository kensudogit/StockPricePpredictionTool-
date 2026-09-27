import { describe, expect, it } from "vitest";
import type { TechnicalResponse } from "@/lib/api";
import { formatBlockReason, isGateHoldMessage } from "@/lib/gate";

describe("TechnicalResponse shape", () => {
  it("accepts snapshot fields used by dashboard", () => {
    const sample: TechnicalResponse = {
      ticker: "7203.T",
      snapshot: { trend: "uptrend", rsi_14: 55, macd: 1.2, adx: 20, atr_14: 3 },
      series: [
        {
          ts: "2024-01-01T00:00:00Z",
          close: 100,
          sma_20: 99,
          ema_12: 99.5,
          rsi_14: 50,
          macd: 0.1,
          bb_upper: 105,
          bb_lower: 95,
          volume: 1000,
        },
      ],
    };
    expect(sample.ticker).toBe("7203.T");
    expect(sample.series[0].close).toBe(100);
  });
});

describe("tv symbol helper logic", () => {
  function tvSymbolFor(ticker: string) {
    if (ticker.endsWith(".T")) return `TSE:${ticker.replace(".T", "")}`;
    if (ticker.startsWith("^")) {
      const map: Record<string, string> = {
        "^N225": "TVC:NI225",
        "^GSPC": "SP:SPX",
        "^IXIC": "NASDAQ:IXIC",
        "^VIX": "TVC:VIX",
      };
      return map[ticker] || ticker.replace("^", "");
    }
    return ticker;
  }

  it("maps JP ticker to TSE", () => {
    expect(tvSymbolFor("7203.T")).toBe("TSE:7203");
  });

  it("maps Nikkei index", () => {
    expect(tvSymbolFor("^N225")).toBe("TVC:NI225");
  });
});

describe("gate hold copy", () => {
  it("translates English dual-window dump", () => {
    const raw =
      "min(short_ev,long_ev)=0.000066 < 0.00080; long oos_strategy_return <= 0; long hit_z -1.00 < 1.00; 20d momentum not up";
    expect(isGateHoldMessage(raw)).toBe(true);
    const ja = formatBlockReason(raw);
    expect(ja).toContain("期待値");
    expect(ja).toContain("モメンタム");
    expect(ja).not.toContain("short_ev");
  });
});
