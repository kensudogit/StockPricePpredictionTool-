"use client";

import { useMemo, useState } from "react";
import type { OrderPreview, Position, ProfitPlan } from "@/lib/api";
import styles from "./trade.module.css";

type OrderArgs = {
  side: "buy" | "sell";
  quantity: number;
  broker: string;
  orderType: string;
  limitPrice?: number;
};

type Props = {
  ticker: string;
  lastPrice?: number | null;
  mode?: string;
  liveAllowed?: boolean;
  liveVenue?: string;
  feeBps?: number;
  brokers: { name: string; available: boolean }[];
  positions: Position[];
  busy: boolean;
  plan?: ProfitPlan | null;
  onEvaluate?: (args: OrderArgs) => Promise<OrderPreview>;
  onSubmit: (args: OrderArgs) => Promise<void>;
};

export function TradePanel({
  ticker,
  lastPrice,
  mode = "paper",
  liveAllowed = false,
  liveVenue,
  feeBps,
  brokers,
  positions,
  busy,
  plan,
  onEvaluate,
  onSubmit,
}: Props) {
  const [quantity, setQuantity] = useState(100);
  const [broker, setBroker] = useState("paper");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [preview, setPreview] = useState<OrderPreview | null>(null);

  const availableBrokers = useMemo(() => {
    const list = brokers.length ? brokers : [{ name: "paper", available: true }];
    return list;
  }, [brokers]);

  const pos = positions.find((p) => p.ticker === ticker);
  const notional =
    quantity * (orderType === "limit" && limitPrice ? Number(limitPrice) : lastPrice || 0);

  const submit = async (side: "buy" | "sell") => {
    if (!quantity || quantity <= 0) return;
    await onSubmit({
      side,
      quantity,
      broker,
      orderType,
      limitPrice: orderType === "limit" && limitPrice ? Number(limitPrice) : undefined,
    });
  };

  return (
    <article className={styles.wrap}>
      <header className={styles.header}>
        <div>
          <h2>売買（手動発注）</h2>
          <p className={styles.sub}>
            {ticker}
            {lastPrice != null ? ` · 直近 ${lastPrice.toLocaleString()} ` : " · 価格未取得 "}
            · mode: {mode}
            {feeBps != null ? ` · 手数料 ${feeBps}bps` : ""}
            {mode === "live" && !liveAllowed
              ? ` · live 不可 (${liveVenue ?? "blocked"})`
              : liveAllowed
                ? ` · live ${liveVenue}`
                : ""}
          </p>
        </div>
        {pos && (
          <div className={styles.posBadge}>
            保有 <strong>{pos.quantity}</strong>
            {pos.avg_cost != null && <span> @ {pos.avg_cost.toFixed(1)}</span>}
          </div>
        )}
      </header>

      <div className={styles.form}>
        <label className={styles.field}>
          <span>数量</span>
          <input
            type="number"
            min={1}
            step={1}
            value={quantity}
            disabled={busy}
            onChange={(e) => setQuantity(Number(e.target.value))}
          />
        </label>
        <label className={styles.field}>
          <span>ブローカー</span>
          <select value={broker} disabled={busy} onChange={(e) => setBroker(e.target.value)}>
            {availableBrokers.map((b) => (
              <option key={b.name} value={b.name}>
                {b.name}
                {b.available ? "" : " (未設定)"}
              </option>
            ))}
          </select>
        </label>
        <label className={styles.field}>
          <span>注文種別</span>
          <select
            value={orderType}
            disabled={busy}
            onChange={(e) => setOrderType(e.target.value as "market" | "limit")}
          >
            <option value="market">成行</option>
            <option value="limit">指値</option>
          </select>
        </label>
        {orderType === "limit" && (
          <label className={styles.field}>
            <span>指値</span>
            <input
              type="number"
              min={0}
              step={0.1}
              value={limitPrice}
              disabled={busy}
              placeholder={lastPrice != null ? String(lastPrice) : ""}
              onChange={(e) => setLimitPrice(e.target.value)}
            />
          </label>
        )}
      </div>

      {plan && (
        <p className={styles.notional}>
          利益関門: {plan.ok ? `通過（${plan.action}）` : "見送り"}
          {plan.expected_value != null ? ` · EV ${(plan.expected_value * 10000).toFixed(1)}bps` : ""}
          {plan.expected_yen != null ? ` · 期待 ${Math.round(plan.expected_yen).toLocaleString()}円` : ""}
          {plan.suggested_qty ? ` · 推奨 ${plan.suggested_qty}株` : ""}
          {plan.block_reason ? ` · ${plan.block_reason}` : ""}
          {plan.suggested_qty ? (
            <>
              {" "}
              <button
                type="button"
                className={styles.evaluate}
                disabled={busy}
                onClick={() => setQuantity(Math.max(1, Math.floor(plan.suggested_qty || 0)))}
              >
                推奨数量を入れる
              </button>
            </>
          ) : null}
        </p>
      )}

      <p className={styles.notional}>
        概算約定金額:{" "}
        <strong>{notional > 0 ? Math.round(notional).toLocaleString() : "—"}</strong>
        {mode === "paper" && <span className={styles.hint}>（paper: 実口座には発注しません。手数料込みで約定）</span>}
        {mode === "live" && !liveAllowed && (
          <span className={styles.hint}>LIVE_TRADING_CONFIRM と実装済みブローカー（alpaca）が必要です</span>
        )}
      </p>

      {preview && (
        <p className={styles.notional}>
          評価: {preview.decision} · 見込み {preview.expected_fill_price.toFixed(2)} · 関門{" "}
          {preview.gate_ok ? "通過" : preview.gate_reason} · リスク{" "}
          {preview.risk_ok ? "OK" : preview.risk_reason}
        </p>
      )}

      <div className={styles.actions}>
        {onEvaluate && (
          <button
            type="button"
            className={styles.evaluate}
            disabled={busy || quantity <= 0}
            onClick={() => {
              void (async () => {
                const next = await onEvaluate({
                  side: "buy",
                  quantity,
                  broker,
                  orderType,
                  limitPrice: orderType === "limit" && limitPrice ? Number(limitPrice) : undefined,
                });
                setPreview(next);
              })();
            }}
          >
            発注評価
          </button>
        )}
        <button
          type="button"
          className={styles.buy}
          disabled={busy || quantity <= 0}
          onClick={() => void submit("buy")}
        >
          買う
        </button>
        <button
          type="button"
          className={styles.sell}
          disabled={busy || quantity <= 0}
          onClick={() => void submit("sell")}
        >
          売る
        </button>
      </div>
    </article>
  );
}
