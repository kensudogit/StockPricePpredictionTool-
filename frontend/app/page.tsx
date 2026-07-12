"use client";

import { useCallback, useEffect, useState } from "react";
import { AnalysisCharts } from "@/components/AnalysisCharts";
import {
  api,
  type BacktestResult,
  type Fundamentals,
  type Health,
  type NewsItem,
  type Order,
  type PipelineResult,
  type Position,
  type Prediction,
  type RiskEvent,
  type Signal,
  type SnsPost,
  type Symbol,
  type TechnicalResponse,
} from "@/lib/api";
import styles from "./page.module.css";

const DEFAULT_TICKER = "7203.T";

function tvSymbolFor(ticker: string) {
  if (ticker.endsWith(".T")) return `TSE:${ticker.replace(".T", "")}`;
  if (ticker.startsWith("^")) return ticker;
  return ticker;
}

export default function DashboardPage() {
  const [ticker, setTicker] = useState(DEFAULT_TICKER);
  const [health, setHealth] = useState<Health | null>(null);
  const [symbols, setSymbols] = useState<Symbol[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [risk, setRisk] = useState<RiskEvent[]>([]);
  const [sns, setSns] = useState<SnsPost[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [technical, setTechnical] = useState<TechnicalResponse | null>(null);
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [ml, setMl] = useState<Record<string, unknown> | null>(null);
  const [dl, setDl] = useState<Record<string, unknown> | null>(null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [brokers, setBrokers] = useState<{ name: string; available: boolean }[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState<PipelineResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ragAnswer, setRagAnswer] = useState<string | null>(null);

  const refresh = useCallback(async (selected = ticker) => {
    setError(null);
    const settled = await Promise.allSettled([
      api.health(),
      api.symbols(),
      api.predictions(),
      api.signals(),
      api.orders(),
      api.positions(),
      api.risk(),
      api.sns(),
      api.news(),
      api.brokers(),
    ]);
    const val = <T,>(i: number, fallback: T): T =>
      settled[i].status === "fulfilled" ? (settled[i] as PromiseFulfilledResult<T>).value : fallback;

    setHealth(val(0, null as Health | null));
    setSymbols(val(1, [] as Symbol[]));
    setPredictions(val(2, [] as Prediction[]));
    setSignals(val(3, [] as Signal[]));
    setOrders(val(4, [] as Order[]));
    setPositions(val(5, [] as Position[]));
    setRisk(val(6, [] as RiskEvent[]));
    setSns(val(7, [] as SnsPost[]));
    setNews(val(8, [] as NewsItem[]));
    setBrokers(val(9, [] as { name: string; available: boolean }[]));

    const failed = settled.filter((r) => r.status === "rejected");
    if (failed.length === settled.length) {
      const reason = (failed[0] as PromiseRejectedResult).reason;
      setError(reason instanceof Error ? reason.message : "API接続に失敗しました");
    } else if (failed.length > 0) {
      setError(`${failed.length} 件のAPIが失敗しました（他は表示中）。再デプロイ後に「更新」してください。`);
    }

    try {
      setTechnical(await api.technical(selected));
    } catch {
      setTechnical(null);
    }
    try {
      setFundamentals(await api.fundamentals(selected));
    } catch {
      setFundamentals(null);
    }
  }, [ticker]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await fn();
      setMessage(label);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : label + " 失敗");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className={styles.page}>
      <header className={styles.hero}>
        <div className={styles.brandBlock}>
          <p className={styles.brand}>StockAI</p>
          <h1 className={styles.headline}>分析・予測・売買・バックテストを一つの画面で。</h1>
          <p className={styles.sub}>
            テクニカル / ファンダ / ニュースLLM / ML・DL / RAG / リスク / 証券API
          </p>
        </div>
        <div className={styles.status}>
          <a className={styles.pill} href="/tests/">
            テスト結果
          </a>
          <div className={styles.pill}>
            <span className={health?.status === "ok" ? styles.dotOk : styles.dotBad} />
            API {health?.status ?? "…"}
          </div>
          <div className={styles.pill}>mode: {health?.trading_mode ?? "—"}</div>
        </div>
      </header>

      <section className={styles.controls}>
        <label className={styles.field}>
          <span>銘柄</span>
          <select value={ticker} onChange={(e) => setTicker(e.target.value)}>
            {(symbols.length ? symbols : [{ ticker: DEFAULT_TICKER } as Symbol]).map((s) => (
              <option key={s.ticker} value={s.ticker}>
                {s.ticker} {s.name ? `— ${s.name}` : ""}
              </option>
            ))}
          </select>
        </label>
        <button className={styles.btnGhost} disabled={busy} onClick={() => refresh()}>更新</button>
        <button className={styles.btnGhost} disabled={busy} onClick={() => run("データ取込完了", () => api.ingest(ticker))}>
          データ取込
        </button>
        <button className={styles.btnGhost} disabled={busy} onClick={() => run("ファンダ取込", () => api.fundamentalsIngest(ticker))}>
          ファンダ
        </button>
        <button className={styles.btnGhost} disabled={busy} onClick={() => run("ニュース収集", () => api.newsCollect(ticker))}>
          ニュース
        </button>
        <button
          className={styles.btnGhost}
          disabled={busy}
          onClick={() =>
            run("ML予測", async () => {
              setMl(await api.mlPredict(ticker));
            })
          }
        >
          ML予測
        </button>
        <button
          className={styles.btnGhost}
          disabled={busy}
          onClick={() =>
            run("DL予測", async () => {
              setDl(await api.dlPredict(ticker, "lstm"));
            })
          }
        >
          DL(LSTM)
        </button>
        <button
          className={styles.btnGhost}
          disabled={busy}
          onClick={() =>
            run("バックテスト", async () => {
              setBacktest(await api.backtest(ticker, "pandas"));
            })
          }
        >
          バックテスト
        </button>
        <button
          className={styles.btnGhost}
          disabled={busy}
          onClick={() =>
            run("RAG", async () => {
              const res = await api.ragQuery(`${ticker} の直近ニュースと注目点は？`);
              setRagAnswer(res.answer || "");
            })
          }
        >
          RAG質問
        </button>
        <button
          className={styles.btnPrimary}
          disabled={busy}
          onClick={() =>
            run("パイプライン完了", async () => {
              setPipeline(await api.runPipeline(ticker));
            })
          }
        >
          {busy ? "実行中…" : "フルパイプライン"}
        </button>
      </section>

      {(message || error) && <p className={error ? styles.error : styles.message}>{error || message}</p>}

      <AnalysisCharts
        technical={technical}
        equityCurve={backtest?.equity_curve}
        tvSymbol={tvSymbolFor(ticker)}
      />

      <section className={styles.grid}>
        <article className={styles.panel}>
          <h2>テクニカル（最新）</h2>
          <ul className={styles.list}>
            {technical ? (
              <>
                <li><span>Trend</span><strong>{String(technical.snapshot.trend)}</strong></li>
                <li><span>RSI</span><strong className={styles.mono}>{Number(technical.snapshot.rsi_14).toFixed(1)}</strong></li>
                <li><span>MACD</span><strong className={styles.mono}>{Number(technical.snapshot.macd).toFixed(2)}</strong></li>
                <li><span>ADX</span><strong className={styles.mono}>{Number(technical.snapshot.adx).toFixed(1)}</strong></li>
                <li><span>ATR</span><strong className={styles.mono}>{Number(technical.snapshot.atr_14).toFixed(2)}</strong></li>
              </>
            ) : (
              <li className={styles.empty}>データ取込後に表示</li>
            )}
          </ul>
        </article>

        <article className={styles.panel}>
          <h2>ファンダメンタル</h2>
          <ul className={styles.list}>
            {fundamentals ? (
              <>
                <li><span>PER</span><strong className={styles.mono}>{fundamentals.per?.toFixed(2) ?? "—"}</strong></li>
                <li><span>PBR</span><strong className={styles.mono}>{fundamentals.pbr?.toFixed(2) ?? "—"}</strong></li>
                <li><span>ROE</span><strong className={styles.mono}>{fundamentals.roe != null ? (fundamentals.roe * 100).toFixed(1) + "%" : "—"}</strong></li>
                <li><span>ROA</span><strong className={styles.mono}>{fundamentals.roa != null ? (fundamentals.roa * 100).toFixed(1) + "%" : "—"}</strong></li>
                <li><span>EPS</span><strong className={styles.mono}>{fundamentals.eps?.toFixed(2) ?? "—"}</strong></li>
                <li><span>営業利益率</span><strong className={styles.mono}>{fundamentals.operating_margin != null ? (fundamentals.operating_margin * 100).toFixed(1) + "%" : "—"}</strong></li>
              </>
            ) : (
              <li className={styles.empty}>「ファンダ」で取得</li>
            )}
          </ul>
        </article>

        <article className={styles.panel}>
          <h2>ML / DL 予測</h2>
          <ul className={styles.list}>
            {ml && (
              <li>
                <span>ML合意</span>
                <strong>{String((ml as { consensus_signal?: string }).consensus_signal ?? "—")}</strong>
              </li>
            )}
            {ml && (
              <li>
                <span>上昇率</span>
                <strong className={styles.mono}>
                  {(((ml as { upside_rate?: number }).upside_rate ?? 0) * 100).toFixed(2)}%
                </strong>
              </li>
            )}
            {dl && (
              <li>
                <span>DL {String((dl as { model?: string }).model)}</span>
                <strong className={(dl as { direction?: string }).direction === "up" ? styles.up : styles.down}>
                  {String((dl as { direction?: string }).direction)}{" "}
                  {(((dl as { predicted_return?: number }).predicted_return ?? 0) * 100).toFixed(2)}%
                </strong>
              </li>
            )}
            {!ml && !dl && <li className={styles.empty}>ML予測 / DL(LSTM) を実行</li>}
          </ul>
        </article>

        <article className={styles.panel}>
          <h2>バックテスト</h2>
          <ul className={styles.list}>
            {backtest ? (
              <>
                <li><span>Engine</span><strong>{backtest.engine}</strong></li>
                <li><span>Return</span><strong className={styles.mono}>{((backtest.metrics.total_return ?? 0) * 100).toFixed(2)}%</strong></li>
                <li><span>Sharpe</span><strong className={styles.mono}>{Number(backtest.metrics.sharpe ?? 0).toFixed(2)}</strong></li>
                <li><span>MaxDD</span><strong className={styles.mono}>{((backtest.metrics.max_drawdown ?? 0) * 100).toFixed(2)}%</strong></li>
              </>
            ) : (
              <li className={styles.empty}>「バックテスト」で実行</li>
            )}
          </ul>
        </article>

        <article className={styles.panel}>
          <h2>ブローカー</h2>
          <ul className={styles.list}>
            {brokers.map((b) => (
              <li key={b.name}>
                <span>{b.name}</span>
                <span className={b.available ? styles.up : styles.muted}>{b.available ? "ready" : "stub/key"}</span>
              </li>
            ))}
          </ul>
        </article>

        <article className={styles.panel}>
          <h2>ポジション / リスク</h2>
          <ul className={styles.list}>
            {positions.map((p) => (
              <li key={p.id}>
                <span>{p.ticker ?? p.symbol_id}</span>
                <strong className={styles.mono}>{p.quantity}</strong>
              </li>
            ))}
            {risk.slice(0, 3).map((r) => (
              <li key={r.id}>
                <span className={r.severity === "critical" ? styles.down : styles.warn}>{r.event_type}</span>
                <span className={styles.muted}>{r.message.slice(0, 28)}</span>
              </li>
            ))}
            {positions.length === 0 && risk.length === 0 && <li className={styles.empty}>フラット</li>}
          </ul>
        </article>

        <article className={styles.panelWide}>
          <h2>ニュース分析</h2>
          <ul className={styles.list}>
            {news.slice(0, 8).map((n) => (
              <li key={n.id}>
                <span>
                  <em className={styles.muted}>[{n.source}/{n.category}]</em> {n.title.slice(0, 80)}
                </span>
                <span className={n.sentiment_label === "positive" ? styles.up : n.sentiment_label === "negative" ? styles.down : styles.muted}>
                  {n.sentiment_label ?? "—"}
                </span>
              </li>
            ))}
            {news.length === 0 && <li className={styles.empty}>「ニュース」で収集（日経/ロイター/Bloomberg/SEC/SNS）</li>}
          </ul>
        </article>

        {(ragAnswer || pipeline || sns.length > 0) && (
          <article className={styles.panelWide}>
            <h2>RAG / パイプライン / SNS</h2>
            {ragAnswer && <pre className={styles.code}>{ragAnswer}</pre>}
            {pipeline && <pre className={styles.code}>{JSON.stringify(pipeline, null, 2)}</pre>}
            <div className={styles.snsGrid}>
              {sns.slice(0, 3).map((p) => (
                <pre key={p.id} className={styles.snsCard}>{p.content}</pre>
              ))}
            </div>
          </article>
        )}

        <article className={styles.panel}>
          <h2>シグナル / 注文</h2>
          <ul className={styles.list}>
            {signals.slice(0, 3).map((s) => (
              <li key={s.id}><span>{s.signal_type}</span><span className={styles.muted}>{s.status}</span></li>
            ))}
            {orders.slice(0, 3).map((o) => (
              <li key={o.id}><span>{o.side}×{o.quantity}</span><span className={styles.muted}>{o.mode}</span></li>
            ))}
            {predictions.slice(0, 2).map((p) => (
              <li key={p.id}>
                <span className={p.direction === "up" ? styles.up : styles.down}>{p.direction}</span>
                <span className={styles.mono}>{p.predicted_price?.toFixed(1)}</span>
              </li>
            ))}
          </ul>
        </article>
      </section>
    </main>
  );
}
