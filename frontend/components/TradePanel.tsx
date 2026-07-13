"use client";

import { useMemo, useState } from "react";
import type { Position } from "@/lib/api";
import styles from "./trade.module.css";

type Props = {
  ticker: string;
  lastPrice?: number | null;
  mode?: string;
  brokers: { name: string; available: boolean }[];
  positions: Position[];
  busy: boolean;
  onSubmit: (args: {
    side: "buy" | "sell";
    quantity: number;
    broker: string;
    orderType: string;
    limitPrice?: number;
  }) => Promise<void>;
};

export function TradePanel({
  ticker,
  lastPrice,
  mode = "paper",
  brokers,
  positions,
  busy,
  onSubmit,
}: Props) {
  const [quantity, setQuantity] = useState(100);
  const [broker, setBroker] = useState("paper");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");

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

      <p className={styles.notional}>
        概算約定金額:{" "}
        <strong>{notional > 0 ? Math.round(notional).toLocaleString() : "—"}</strong>
        {mode === "paper" && <span className={styles.hint}>（paper: 実口座には発注しません）</span>}
      </p>

      <div className={styles.actions}>
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
