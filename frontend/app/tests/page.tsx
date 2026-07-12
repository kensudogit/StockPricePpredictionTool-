"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "../page.module.css";

type Case = {
  class: string;
  name: string;
  time: number;
  status: string;
  message?: string;
};

type SideSummary = {
  suite?: string;
  exit_code?: number;
  total?: number;
  passed?: number;
  failed?: number;
  skipped?: number;
  html_report?: string | null;
  suites?: { name: string; cases: Case[] }[];
  message?: string;
  status?: string;
};

type Summary = {
  status?: string;
  message?: string;
  generated_at?: string;
  backend?: SideSummary;
  frontend?: SideSummary;
  totals?: {
    total: number;
    passed: number;
    failed: number;
    skipped: number;
    ok: boolean;
  };
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function TestsPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`${API}/api/v1/tests/summary`, { cache: "no-store" });
      const data = await res.json();
      setSummary(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runTests = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/v1/tests/run?wait=true`, { method: "POST" });
      const data = await res.json();
      if (data.summary) setSummary(data.summary);
      else await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "run failed");
    } finally {
      setBusy(false);
    }
  };

  const cases: { side: string; c: Case }[] = [];
  for (const side of ["backend", "frontend"] as const) {
    const block = summary?.[side];
    for (const suite of block?.suites || []) {
      for (const c of suite.cases || []) {
        cases.push({ side, c });
      }
    }
  }

  const totals = summary?.totals;

  return (
    <main className={styles.page}>
      <header className={styles.hero}>
        <div>
          <p className={styles.brand}>StockAI</p>
          <h1 className={styles.headline}>テスト結果</h1>
          <p className={styles.sub}>Python (pytest) / TypeScript (vitest) の実行結果を確認できます。</p>
        </div>
        <div className={styles.status}>
          <a className={styles.pill} href="/">
            ← ダッシュボード
          </a>
          <a className={styles.pill} href="/api/v1/tests/report" target="_blank" rel="noreferrer">
            HTMLレポート
          </a>
          <a className={styles.pill} href="/test-results/" target="_blank" rel="noreferrer">
            /test-results
          </a>
        </div>
      </header>

      <section className={styles.controls}>
        <button className={styles.btnGhost} disabled={busy} onClick={load}>
          再読込
        </button>
        <button className={styles.btnPrimary} disabled={busy} onClick={runTests}>
          {busy ? "実行中…" : "全テスト実行"}
        </button>
      </section>

      {error && <p className={styles.error}>{error}</p>}
      {summary?.status === "missing" && <p className={styles.message}>{summary.message}</p>}

      {totals && (
        <section className={styles.grid}>
          <article className={styles.panel}>
            <h2>合計</h2>
            <ul className={styles.list}>
              <li>
                <span>Overall</span>
                <strong className={totals.ok ? styles.up : styles.down}>{totals.ok ? "PASS" : "FAIL"}</strong>
              </li>
              <li>
                <span>Total</span>
                <strong className={styles.mono}>{totals.total}</strong>
              </li>
              <li>
                <span>Passed</span>
                <strong className={styles.up}>{totals.passed}</strong>
              </li>
              <li>
                <span>Failed</span>
                <strong className={styles.down}>{totals.failed}</strong>
              </li>
              <li>
                <span>Skipped</span>
                <strong className={styles.warn}>{totals.skipped}</strong>
              </li>
            </ul>
            {summary?.generated_at && <p className={styles.muted}>{summary.generated_at}</p>}
          </article>
          <article className={styles.panel}>
            <h2>Backend</h2>
            <ul className={styles.list}>
              <li>
                <span>passed/failed</span>
                <strong>
                  {summary?.backend?.passed ?? 0}/{summary?.backend?.failed ?? 0}
                </strong>
              </li>
              <li>
                <span>report</span>
                <a href="/api/v1/tests/files/backend-pytest.html">HTML</a>
              </li>
            </ul>
          </article>
          <article className={styles.panel}>
            <h2>Frontend</h2>
            <ul className={styles.list}>
              <li>
                <span>passed/failed</span>
                <strong>
                  {summary?.frontend?.passed ?? 0}/{summary?.frontend?.failed ?? 0}
                </strong>
              </li>
              <li>
                <span>report</span>
                <a href="/api/v1/tests/files/frontend-vitest.html">HTML</a>
              </li>
            </ul>
          </article>
        </section>
      )}

      <section className={styles.grid} style={{ marginTop: "1rem" }}>
        <article className={styles.panelWide}>
          <h2>ケース一覧</h2>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
              <thead>
                <tr>
                  <th align="left">Side</th>
                  <th align="left">Class</th>
                  <th align="left">Test</th>
                  <th align="left">Status</th>
                  <th align="left">Time</th>
                </tr>
              </thead>
              <tbody>
                {cases.length === 0 && (
                  <tr>
                    <td colSpan={5} className={styles.empty}>
                      結果がありません。「全テスト実行」を押してください。
                    </td>
                  </tr>
                )}
                {cases.map(({ side, c }, i) => (
                  <tr key={`${side}-${c.class}-${c.name}-${i}`} style={{ borderTop: "1px solid #2a3a32" }}>
                    <td>{side}</td>
                    <td>{c.class}</td>
                    <td>{c.name}</td>
                    <td className={c.status === "passed" ? styles.up : c.status === "failed" || c.status === "error" ? styles.down : styles.warn}>
                      {c.status}
                    </td>
                    <td className={styles.mono}>{c.time?.toFixed?.(3) ?? c.time}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </main>
  );
}
