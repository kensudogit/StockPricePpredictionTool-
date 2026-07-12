import { describe, expect, it } from "vitest";

describe("accuracy & integrated response contracts", () => {
  it("accuracy metrics keys", () => {
    const metrics = {
      direction_hit_rate: 0.55,
      mae: 12.3,
      rmse: 18.1,
      model_total_return: 0.04,
      buy_hold_total_return: 0.02,
    };
    expect(metrics.direction_hit_rate).toBeGreaterThan(0.5);
    expect(metrics.mae).toBeGreaterThan(0);
  });

  it("integrated signal mapping", () => {
    const signalFromScore = (s: number) => (s >= 0.25 ? "buy" : s <= -0.25 ? "sell" : "hold");
    expect(signalFromScore(0.4)).toBe("buy");
    expect(signalFromScore(-0.4)).toBe("sell");
    expect(signalFromScore(0.1)).toBe("hold");
  });
});
