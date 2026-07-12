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
import type { AccuracyResult, BacktestResult, TechnicalResponse } from "@/lib/api";
import styles from "./charts.module.css";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

type Props = {
  technical: TechnicalResponse | null;
  backtest?: BacktestResult | null;
  accuracy?: AccuracyResult | null;
  tvSymbol?: string;
};

export function AnalysisCharts({
  technical,
  backtest = null,
  accuracy = null,
  tvSymbol = "TSE:7203",
}: Props) {
  const series = technical?.series ?? [];
  const equityCurve = backtest?.equity_curve ?? [];
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

  const equityOption = useMemo(() => {
    const dates = equityCurve.map((e) => String(e.ts).slice(0, 10));
    const hasBh = equityCurve.some((e) => e.buy_hold != null);
    const hasDd = equityCurve.some((e) => e.drawdown != null);
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      legend: {
        data: ["Strategy", ...(hasBh ? ["Buy&Hold"] : []), ...(hasDd ? ["Drawdown"] : [])],
        textStyle: { color: "#8aa396" },
      },
      grid: [
        { left: 50, right: 20, top: 40, height: hasDd ? "52%" : "70%" },
        ...(hasDd ? [{ left: 50, right: 20, top: "68%", height: "20%" }] : []),
      ],
      xAxis: [
        { type: "category", data: dates, axisLabel: { color: "#8aa396" }, gridIndex: 0 },
        ...(hasDd
          ? [{ type: "category", data: dates, axisLabel: { show: false }, gridIndex: 1 }]
          : []),
      ],
      yAxis: [
        {
          type: "value",
          scale: true,
          axisLabel: { color: "#8aa396" },
          splitLine: { lineStyle: { color: "#2a3a32" } },
          gridIndex: 0,
        },
        ...(hasDd
          ? [
              {
                type: "value",
                scale: true,
                axisLabel: { color: "#8aa396", formatter: (v: number) => `${(v * 100).toFixed(0)}%` },
                splitLine: { show: false },
                gridIndex: 1,
              },
            ]
          : []),
      ],
      series: [
        {
          name: "Strategy",
          type: "line",
          data: equityCurve.map((e) => e.equity),
          showSymbol: false,
          areaStyle: { color: "rgba(61,214,140,0.15)" },
          lineStyle: { color: "#3dd68c" },
          xAxisIndex: 0,
          yAxisIndex: 0,
        },
        ...(hasBh
          ? [
              {
                name: "Buy&Hold",
                type: "line",
                data: equityCurve.map((e) => e.buy_hold ?? null),
                showSymbol: false,
                lineStyle: { color: "#6b9fff", type: "dashed" },
                xAxisIndex: 0,
                yAxisIndex: 0,
              },
            ]
          : []),
        ...(hasDd
          ? [
              {
                name: "Drawdown",
                type: "line",
                data: equityCurve.map((e) => e.drawdown ?? null),
                showSymbol: false,
                areaStyle: { color: "rgba(232,93,93,0.2)" },
                lineStyle: { color: "#e85d5d" },
                xAxisIndex: 1,
                yAxisIndex: 1,
              },
            ]
          : []),
      ],
    };
  }, [equityCurve]);

  const accuracyPriceOption = useMemo(() => {
    const pts = accuracy?.series ?? [];
    const dates = pts.map((p) => String(p.ts).slice(0, 10));
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      legend: { data: ["Predicted", "Actual"], textStyle: { color: "#8aa396" } },
      xAxis: { type: "category", data: dates, axisLabel: { color: "#8aa396" } },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#8aa396" },
        splitLine: { lineStyle: { color: "#2a3a32" } },
      },
      series: [
        {
          name: "Predicted",
          type: "line",
          data: pts.map((p) => p.predicted_price),
          showSymbol: false,
          lineStyle: { color: "#e8b84a" },
        },
        {
          name: "Actual",
          type: "line",
          data: pts.map((p) => p.actual_price),
          showSymbol: false,
          lineStyle: { color: "#3dd68c" },
        },
      ],
    };
  }, [accuracy]);

  const accuracyEquityOption = useMemo(() => {
    const pts = accuracy?.series ?? [];
    const dates = pts.map((p) => String(p.ts).slice(0, 10));
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      legend: { data: ["Model", "Buy&Hold"], textStyle: { color: "#8aa396" } },
      xAxis: { type: "category", data: dates, axisLabel: { color: "#8aa396" } },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#8aa396" },
        splitLine: { lineStyle: { color: "#2a3a32" } },
      },
      series: [
        {
          name: "Model",
          type: "line",
          data: pts.map((p) => p.model_equity),
          showSymbol: false,
          areaStyle: { color: "rgba(232,184,74,0.12)" },
          lineStyle: { color: "#e8b84a" },
        },
        {
          name: "Buy&Hold",
          type: "line",
          data: pts.map((p) => p.buy_hold_equity),
          showSymbol: false,
          lineStyle: { color: "#6b9fff", type: "dashed" },
        },
      ],
    };
  }, [accuracy]);

  useEffect(() => {
    const el = chartRef.current;
    if (!el) return;
    el.innerHTML = "";
    const iframe = document.createElement("iframe");
    const params = new URLSearchParams({
      frameElementId: "tv_chart",
      symbol: tvSymbol,
      interval: "D",
      hidesidetoolbar: "0",
      symboledit: "1",
      saveimage: "0",
      toolbarbg: "1a2420",
      studies: "[]",
      theme: "dark",
      style: "1",
      timezone: "Asia/Tokyo",
      withdateranges: "1",
      hideideas: "1",
      locale: "ja",
    });
    iframe.src = `https://s.tradingview.com/widgetembed/?${params.toString()}`;
    iframe.title = `TradingView ${tvSymbol}`;
    iframe.style.width = "100%";
    iframe.style.height = "420px";
    iframe.style.border = "0";
    iframe.allowFullscreen = true;
    el.appendChild(iframe);
  }, [tvSymbol]);

  const m = accuracy?.metrics;
  const bm = backtest?.metrics;

  return (
    <div className={styles.wrap}>
      <section className={styles.panel}>
        <h3>ECharts — 価格 / ボリンジャー / RSI</h3>
        {series.length ? (
          <ReactECharts option={echartsOption} style={{ height: 360 }} />
        ) : (
          <p className={styles.empty}>テクニカルデータなし（「データ取込」で取得）</p>
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
          <p className={styles.empty}>テクニカルデータなし（「データ取込」で取得）</p>
        )}
      </section>

      <section className={styles.panelWide}>
        <h3>TradingView Widget ({tvSymbol})</h3>
        <div id="tv_chart_container" ref={chartRef} className={styles.tv} />
      </section>

      {equityCurve.length > 0 && (
        <section className={styles.panelWide}>
          <h3>
            Backtest — Strategy vs Buy&Hold / Drawdown
            {bm?.total_return != null && (
              <span className={styles.meta}>
                {" "}
                · Return {(Number(bm.total_return) * 100).toFixed(1)}%
                {bm.buy_hold_return != null && ` · BH ${(Number(bm.buy_hold_return) * 100).toFixed(1)}%`}
                {bm.sharpe != null && ` · Sharpe ${Number(bm.sharpe).toFixed(2)}`}
                {bm.max_drawdown != null && ` · MaxDD ${(Number(bm.max_drawdown) * 100).toFixed(1)}%`}
              </span>
            )}
          </h3>
          <ReactECharts option={equityOption} style={{ height: 320 }} />
        </section>
      )}

      {accuracy && (accuracy.series?.length ?? 0) > 0 && (
        <>
          <section className={styles.panel}>
            <h3>
              予測精度 — Pred vs Actual
              {m?.direction_hit_rate != null && (
                <span className={styles.meta}>
                  {" "}
                  · Hit {(Number(m.direction_hit_rate) * 100).toFixed(1)}%
                  {m.mae != null && ` · MAE ${Number(m.mae).toFixed(1)}`}
                </span>
              )}
            </h3>
            <ReactECharts option={accuracyPriceOption} style={{ height: 280 }} />
          </section>
          <section className={styles.panel}>
            <h3>
              予測精度 — Model Equity
              {m?.model_total_return != null && (
                <span className={styles.meta}>
                  {" "}
                  · Model {(Number(m.model_total_return) * 100).toFixed(1)}%
                  {m.buy_hold_total_return != null &&
                    ` · BH ${(Number(m.buy_hold_total_return) * 100).toFixed(1)}%`}
                </span>
              )}
            </h3>
            <ReactECharts option={accuracyEquityOption} style={{ height: 280 }} />
          </section>
        </>
      )}
    </div>
  );
}
