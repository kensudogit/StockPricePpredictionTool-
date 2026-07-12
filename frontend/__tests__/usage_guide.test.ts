import { describe, expect, it } from "vitest";

describe("UsageGuidePanel content contract", () => {
  const techStack = [
    "Python · FastAPI",
    "PostgreSQL · pgvector",
    "Next.js",
    "ECharts · Chart.js",
    "TradingView",
    "ML · DL · RAG",
  ];

  it("includes core stack tags", () => {
    expect(techStack).toContain("Next.js");
    expect(techStack).toContain("ML · DL · RAG");
  });

  it("recommended flow starts with ticker selection", () => {
    const first = "銘柄を選択（例: 7203.T トヨタ）";
    expect(first.includes("7203.T")).toBe(true);
  });
});
