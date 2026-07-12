"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";
import ReactECharts from "echarts-for-react";
import type { TechnicalResponse } from "@/lib/api";
import styles from "./charts.module.css";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

type Props = {
  technical: TechnicalResponse | null;
  equityCurve?: { ts: string; equity: number }[];
  tvSymbol?: string;
};

export function AnalysisCharts({ technical, equityCurve = [], tvSymbol = "TYO:7203" }: Props) {
  const series = technical?.series ?? [];
  const chartRef = useRef<HTMLDivElement>(null);

  const chartJsData = useMemo(
    () => ({
      labels: series.map((s) => s.ts.slice(0, 10)),
      datasets: [
        {
          label: "Close",
          data: series.map((s) => s.close),
          borderColor: "#3dd68c",
          backgroundColor: "rgba(61,214,140,0.12)",
          fill: true,
          tension: 0.2,
          pointRadius: 0,
        },
        {
          label: "SMA20",
          data: series.map((s) => s.sma_20 ?? null),
          borderColor: "#e8b84a",
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0.2,
        },
      ],
    }),
    [series],
  );

  const echartsOption = useMemo(() => {
    const dates = series.map((s) => s.ts.slice(0, 10));
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      legend: { data: ["Close", "BB Upper", "BB Lower", "RSI"], textStyle: { color: "#8aa396" } },
      grid: [
        { left: 50, right: 20, top: 40, height: "55%" },
        { left: 50, right: 20, top: "72%", height: "18%" },
      ],
      xAxis: [
        { type: "category", data: dates, axisLabel: { color: "#8aa396" }, gridIndex: 0 },
        { type: "category", data: dates, axisLabel: { show: false }, gridIndex: 1 },
      ],
      yAxis: [
        { scale: true, axisLabel: { color: "#8aa396" }, splitLine: { lineStyle: { color: "#2a3a32" } }, gridIndex: 0 },
        { scale: true, min: 0, max: 100, axisLabel: { color: "#8aa396" }, splitLine: { show: false }, gridIndex: 1 },
      ],
      series: [
        {
          name: "Close",
          type: "line",
          data: series.map((s) => s.close),
          showSymbol: false,
          lineStyle: { color: "#3dd68c" },
          xAxisIndex: 0,
          yAxisIndex: 0,
        },
        {
          name: "BB Upper",
          type: "line",
          data: series.map((s) => s.bb_upper),
          showSymbol: false,
          lineStyle: { color: "#6b8f7c", width: 1 },
          xAxisIndex: 0,
          yAxisIndex: 0,
        },
        {
          name: "BB Lower",
          type: "line",
          data: series.map((s) => s.bb_lower),
          showSymbol: false,
          lineStyle: { color: "#6b8f7c", width: 1 },
          xAxisIndex: 0,
          yAxisIndex: 0,
        },
        {
          name: "RSI",
          type: "line",
          data: series.map((s) => s.rsi_14),
          showSymbol: false,
          lineStyle: { color: "#e8b84a" },
          xAxisIndex: 1,
          yAxisIndex: 1,
        },
      ],
    };
  }, [series]);

  const equityOption = useMemo(
    () => ({
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: equityCurve.map((e) => String(e.ts).slice(0, 10)),
        axisLabel: { color: "#8aa396" },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#8aa396" },
        splitLine: { lineStyle: { color: "#2a3a32" } },
      },
      series: [
        {
          type: "line",
          data: equityCurve.map((e) => e.equity),
          showSymbol: false,
          areaStyle: { color: "rgba(61,214,140,0.15)" },
          lineStyle: { color: "#3dd68c" },
        },
      ],
    }),
    [equityCurve],
  );

  useEffect(() => {
    // TradingView advanced chart widget
    const el = chartRef.current;
    if (!el) return;
    el.innerHTML = "";
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => {
      // @ts-expect-error TradingView global
      if (window.TradingView) {
        // @ts-expect-error TradingView global
        new window.TradingView.widget({
          container_id: el.id,
          symbol: tvSymbol,
          interval: "D",
          timezone: "Asia/Tokyo",
          theme: "dark",
          style: "1",
          locale: "ja",
          width: "100%",
          height: 420,
          hide_side_toolbar: false,
          allow_symbol_change: true,
        });
      }
    };
    document.body.appendChild(script);
    return () => {
      script.remove();
    };
  }, [tvSymbol]);

  return (
    <div className={styles.wrap}>
      <section className={styles.panel}>
        <h3>ECharts — 価格 / ボリンジャー / RSI</h3>
        {series.length ? (
          <ReactECharts option={echartsOption} style={{ height: 360 }} />
        ) : (
          <p className={styles.empty}>テクニカルデータなし</p>
        )}
      </section>

      <section className={styles.panel}>
        <h3>Chart.js — Close / SMA20</h3>
        {series.length ? (
          <Line
            data={chartJsData}
            options={{
              responsive: true,
              plugins: { legend: { labels: { color: "#8aa396" } } },
              scales: {
                x: { ticks: { color: "#8aa396", maxTicksLimit: 8 }, grid: { color: "#2a3a32" } },
                y: { ticks: { color: "#8aa396" }, grid: { color: "#2a3a32" } },
              },
            }}
          />
        ) : (
          <p className={styles.empty}>テクニカルデータなし</p>
        )}
      </section>

      <section className={styles.panelWide}>
        <h3>TradingView Widget</h3>
        <div id="tv_chart_container" ref={chartRef} className={styles.tv} />
      </section>

      {equityCurve.length > 0 && (
        <section className={styles.panelWide}>
          <h3>Backtest Equity (ECharts)</h3>
          <ReactECharts option={equityOption} style={{ height: 260 }} />
        </section>
      )}
    </div>
  );
}
