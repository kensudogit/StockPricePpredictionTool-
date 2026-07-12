import { describe, expect, it } from "vitest";
import type { TechnicalResponse } from "@/lib/api";

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
    if (ticker.endsWith(".T")) return `TYO:${ticker.replace(".T", "")}`;
    if (ticker.startsWith("^")) return ticker;
    return ticker;
  }

  it("maps JP ticker to TYO", () => {
    expect(tvSymbolFor("7203.T")).toBe("TYO:7203");
  });

  it("keeps index symbols", () => {
    expect(tvSymbolFor("^N225")).toBe("^N225");
  });
});
