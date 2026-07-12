"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { IntegratedAnalysis } from "@/lib/api";
import styles from "./integrated.module.css";

type Props = {
  data: IntegratedAnalysis | null;
};

export function IntegratedAnalysisPanel({ data }: Props) {
  const radarOption = useMemo(() => {
    const axes = data?.radar ?? [
      { axis: "Technical", value: 0 },
      { axis: "Fundamental", value: 0 },
      { axis: "News", value: 0 },
    ];
    return {
      backgroundColor: "transparent",
      tooltip: {},
      radar: {
        indicator: axes.map((a) => ({ name: a.axis, max: 100 })),
        axisName: { color: "#8aa396" },
        splitLine: { lineStyle: { color: "#2a3a32" } },
        splitArea: { areaStyle: { color: ["rgba(26,36,32,0.4)", "rgba(26,36,32,0.15)"] } },
        axisLine: { lineStyle: { color: "#2a3a32" } },
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: axes.map((a) => a.value),
              name: "Score",
              areaStyle: { color: "rgba(61,214,140,0.25)" },
              lineStyle: { color: "#3dd68c" },
              itemStyle: { color: "#3dd68c" },
            },
          ],
        },
      ],
    };
  }, [data]);

  if (!data) {
    return (
      <article className={styles.wrap}>
        <h2>統合分析（テクニカル × ファンダ × ニュース）</h2>
        <p className={styles.empty}>「統合分析」を実行すると、3領域のスコアと推奨シグナルが表示されます。</p>
      </article>
    );
  }

  const signalClass =
    data.signal === "buy" ? styles.buy : data.signal === "sell" ? styles.sell : styles.hold;

  return (
    <article className={styles.wrap}>
      <header className={styles.header}>
        <div>
          <h2>統合分析（テクニカル × ファンダ × ニュース）</h2>
          <p className={styles.summary}>{data.summary}</p>
        </div>
        <div className={`${styles.signal} ${signalClass}`}>
          <span className={styles.signalLabel}>SIGNAL</span>
          <strong>{data.signal.toUpperCase()}</strong>
          <span className={styles.mono}>{data.composite_score >= 0 ? "+" : ""}{data.composite_score.toFixed(2)}</span>
        </div>
      </header>

      <div className={styles.grid}>
        <div className={styles.radar}>
          <ReactECharts option={radarOption} style={{ height: 260 }} />
        </div>
        <ul className={styles.scores}>
          <li>
            <span>テクニカル</span>
            <strong className={styles.mono}>{data.scores.technical.toFixed(2)}</strong>
          </li>
          <li>
            <span>ファンダ</span>
            <strong className={styles.mono}>{data.scores.fundamental.toFixed(2)}</strong>
          </li>
          <li>
            <span>ニュース</span>
            <strong className={styles.mono}>{data.scores.news.toFixed(2)}</strong>
          </li>
          <li>
            <span>強度</span>
            <strong className={styles.mono}>{(data.strength * 100).toFixed(0)}%</strong>
          </li>
          <li>
            <span>重み</span>
            <strong className={styles.muted}>
              T{Math.round(data.weights.technical * 100)} / F{Math.round(data.weights.fundamental * 100)} / N
              {Math.round(data.weights.news * 100)}
            </strong>
          </li>
        </ul>
      </div>

      <div className={styles.columns}>
        <section>
          <h3>テクニカル</h3>
          <ul>
            {data.technical.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3>ファンダメンタル</h3>
          <ul>
            {data.fundamental.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3>ニュース</h3>
          <ul>
            {data.news.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      </div>
    </article>
  );
}
