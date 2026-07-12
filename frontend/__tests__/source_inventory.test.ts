import { describe, expect, it } from "vitest";
import fs from "fs";
import path from "path";

/**
 * Smoke: ensure every TS/TSX source under app/lib/components is present and non-empty.
 * (Importing React Server Components in vitest is limited; this guards file coverage.)
 */
describe("TypeScript source inventory", () => {
  const root = path.resolve(__dirname, "..");
  const targets = [
    "app/page.tsx",
    "app/layout.tsx",
    "lib/api.ts",
    "components/AnalysisCharts.tsx",
  ];

  it.each(targets)("%s exists and has content", (rel) => {
    const full = path.join(root, rel);
    expect(fs.existsSync(full)).toBe(true);
    const src = fs.readFileSync(full, "utf8");
    expect(src.length).toBeGreaterThan(50);
  });

  it("page exports default component", () => {
    const src = fs.readFileSync(path.join(root, "app/page.tsx"), "utf8");
    expect(src).toContain("export default function");
  });

  it("api exports api object", () => {
    const src = fs.readFileSync(path.join(root, "lib/api.ts"), "utf8");
    expect(src).toContain("export const api");
  });
});
