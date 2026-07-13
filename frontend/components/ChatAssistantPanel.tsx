"use client";

import { useEffect, useRef, useState } from "react";
import { api, type ChatResponse, type InsightResult } from "@/lib/api";
import styles from "./chat.module.css";

type Msg = { role: "user" | "assistant"; content: string };

type Props = {
  ticker: string;
  insight: InsightResult | null;
  busy: boolean;
  setBusy: (v: boolean) => void;
  onError: (msg: string) => void;
};

const SUGGESTIONS = ["なぜ買いなのか？", "主なリスクは？", "ニュース要約を教えて", "バックテストの勝率は？"];

export function ChatAssistantPanel({ ticker, insight, busy, setBusy, onError }: Props) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [suggested, setSuggested] = useState<string[]>(SUGGESTIONS);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sessionId = "web-assistant";

  useEffect(() => {
    void api
      .chatHistory(sessionId)
      .then((rows) => {
        setMessages(
          rows.map((r) => ({
            role: r.role === "assistant" ? "assistant" : "user",
            content: r.content,
          })),
        );
      })
      .catch(() => {
        /* first visit */
      });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setInput("");
    try {
      const res: ChatResponse = await api.chat({
        ticker,
        question: q,
        session_id: sessionId,
      });
      setMessages((m) => [...m, { role: "assistant", content: res.answer }]);
      if (res.suggested?.length) setSuggested(res.suggested);
    } catch (e) {
      onError(e instanceof Error ? e.message : "チャットに失敗しました");
      setMessages((m) => [...m, { role: "assistant", content: "回答に失敗しました。データ取込後に再試行してください。" }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className={styles.wrap}>
      <header className={styles.header}>
        <div>
          <h2>投資アシスタント</h2>
          <p className={styles.sub}>
            {ticker}
            {insight?.signal ? ` · 現在シグナル: ${insight.signal.label}` : ""}
            {" · 「なぜ買い？」「リスクは？」と質問できます"}
          </p>
        </div>
      </header>

      <div className={styles.suggestions}>
        {suggested.map((s) => (
          <button key={s} type="button" className={styles.chip} disabled={busy} onClick={() => void ask(s)}>
            {s}
          </button>
        ))}
      </div>

      <div className={styles.thread} aria-live="polite">
        {messages.length === 0 && (
          <p className={styles.empty}>チャットを開始するか、上の候補を押してください。AIインサイト取得後により的確に答えます。</p>
        )}
        {messages.map((m, i) => (
          <div key={`${m.role}-${i}`} className={m.role === "user" ? styles.user : styles.assistant}>
            <span className={styles.role}>{m.role === "user" ? "You" : "AI"}</span>
            <p>{m.content}</p>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        className={styles.composer}
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <input
          value={input}
          disabled={busy}
          placeholder="例: なぜ買い判断なのか？ 最大リスクは？"
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "…" : "送信"}
        </button>
      </form>
    </article>
  );
}
