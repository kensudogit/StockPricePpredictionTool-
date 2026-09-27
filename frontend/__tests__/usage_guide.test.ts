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

  it("recommended flow starts with EV allocation", () => {
    const first = "「期待配分」で EV 上位だけにリスク予算を割る（全通過銘柄には張らない）";
    expect(first.includes("期待配分")).toBe(true);
  });
});
