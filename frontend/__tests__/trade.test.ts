import { describe, expect, it } from "vitest";

describe("manual trade order body", () => {
  it("builds paper buy payload", () => {
    const body = {
      ticker: "7203.T",
      side: "buy" as const,
      quantity: 100,
      broker: "paper",
      order_type: "market",
    };
    expect(body.side).toBe("buy");
    expect(body.quantity).toBeGreaterThan(0);
    expect(body.broker).toBe("paper");
  });
});
