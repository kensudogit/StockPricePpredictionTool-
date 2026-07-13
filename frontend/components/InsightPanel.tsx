"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { InsightResult } from "@/lib/api";
import styles from "./insight.module.css";

type Props = {
  data: InsightResult | null;
};

export function InsightPanel({ data }: Props) {
  const shapOption = useMemo(() => {
    const feats = (data?.explanation?.features ?? []).slice(0, 8).reverse();
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 110, right: 24, top: 16, bottom: 24 },
      xAxis: {
        type: "value",
        axisLabel: { color: "#8aa396" },
        splitLine: { lineStyle: { color: "#2a3a32" } },
      },
      yAxis: {
        type: "category",
        data: feats.map((f) => f.label),
        axisLabel: { color: "#8aa396", fontSize: 11 },
      },
      series: [
        {
          type: "bar",
          data: feats.map((f) => ({
            value: f.impact,
            itemStyle: { color: f.impact >= 0 ? "#3dd68c" : "#e85d5d" },
          })),
          barWidth: 12,
        },
      ],
    };
  }, [data]);

  if (!data) {
    return (
      <article className={styles.wrap}>
        <h2>AIインサイト</h2>
        <p className={styles.empty}>
          「AIインサイト」を実行すると、予測価格・信頼度・XAI根拠・ニュース要約・バックテスト・売買シグナルがまとめて表示されます。
        </p>
      </article>
    );
  }

  const sig = data.signal.action;
  const sigClass = sig === "buy" ? styles.buy : sig === "sell" ? styles.sell : styles.hold;
  const confPct = Math.round((data.confidence.value ?? 0) * 100);
  const bt = data.backtest?.metrics ?? {};
  const acc = data.accuracy ?? {};

  return (
    <article className={styles.wrap}>
      <header className={styles.header}>
        <div>
          <h2>AIインサイト</h2>
          <p className={styles.sub}>
            {data.ticker} · {data.price.model} · {new Date(data.as_of).toLocaleString("ja-JP")}
          </p>
        </div>
        <div className={`${styles.signal} ${sigClass}`}>
          <span className={styles.signalLabel}>シグナル</span>
          <strong>{data.signal.label}</strong>
          <span className={styles.mono}>{data.signal.action.toUpperCase()}</span>
        </div>
      </header>

      <div className={styles.kpiGrid}>
        <div className={styles.kpi}>
          <span>最終終値</span>
          <strong className={styles.mono}>{data.price.last_close.toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong>
        </div>
        <div className={styles.kpi}>
          <span>予測価格</span>
          <strong className={styles.mono}>
            {data.price.predicted_price.toLocaleString(undefined, { maximumFractionDigits: 1 })}
          </strong>
          <em className={data.price.predicted_return >= 0 ? styles.up : styles.down}>
            {(data.price.predicted_return * 100).toFixed(2)}%
          </em>
        </div>
        <div className={styles.kpi}>
          <span>信頼度</span>
          <strong className={styles.mono}>{confPct}%</strong>
          <em>{data.confidence.label}</em>
          <div className={styles.barTrack}>
            <div className={styles.barFill} style={{ width: `${confPct}%` }} />
          </div>
        </div>
        <div className={styles.kpi}>
          <span>方向</span>
          <strong className={data.price.direction === "up" ? styles.up : styles.down}>
            {data.price.direction}
          </strong>
        </div>
      </div>

      <div className={styles.split}>
        <section>
          <h3>Explainable AI（{data.explanation.method}）</h3>
          <p className={styles.note}>{data.explanation.note}</p>
          <ReactECharts option={shapOption} style={{ height: 260 }} />
          <ul className={styles.narrative}>
            {data.narrative.slice(0, 6).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>

        <section>
          <h3>AIニュース要約</h3>
          <p className={styles.newsSummary}>{data.news.summary}</p>
          <ul className={styles.articles}>
            {data.news.articles.slice(0, 4).map((a) => (
              <li key={a.id}>
                <span className={styles.muted}>[{a.sentiment_label ?? "—"}]</span> {a.title}
              </li>
            ))}
          </ul>

          <h3 className={styles.mt}>バックテスト結果</h3>
          <ul className={styles.metrics}>
            <li>
              <span>勝率</span>
              <strong>{bt.win_rate != null ? `${(Number(bt.win_rate) * 100).toFixed(1)}%` : "—"}</strong>
            </li>
            <li>
              <span>リターン</span>
              <strong>{bt.total_return != null ? `${(Number(bt.total_return) * 100).toFixed(1)}%` : "—"}</strong>
            </li>
            <li>
              <span>MaxDD</span>
              <strong>{bt.max_drawdown != null ? `${(Number(bt.max_drawdown) * 100).toFixed(1)}%` : "—"}</strong>
            </li>
            <li>
              <span>Sharpe</span>
              <strong>{bt.sharpe != null ? Number(bt.sharpe).toFixed(2) : "—"}</strong>
            </li>
            <li>
              <span>WF的中率</span>
              <strong>
                {acc.direction_hit_rate != null
                  ? `${(Number(acc.direction_hit_rate) * 100).toFixed(1)}% (n=${acc.n_samples ?? 0})`
                  : "—"}
              </strong>
            </li>
          </ul>
        </section>
      </div>
    </article>
  );
}
