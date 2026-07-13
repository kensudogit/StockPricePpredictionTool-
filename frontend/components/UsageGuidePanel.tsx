"use client";

import { useCallback, useRef, useState } from "react";
import styles from "./UsageGuidePanel.module.css";

const techStack = [
  "Python · FastAPI",
  "PostgreSQL · pgvector",
  "Next.js",
  "ECharts · Chart.js",
  "TradingView",
  "ML · DL · RAG",
] as const;

const archDiagram = `銘柄選択
    │
    ▼
データ取込 (Yahoo Chart API / Stooq)
    │ OHLCV → PostgreSQL
    ▼
テクニカル / ファンダ / ニュースLLM
    │
    ▼
ML予測 · DL(LSTM) · RAG質問
    │
    ▼
バックテスト · リスク · 証券API (paper)
    │
    ▼
フルパイプライン / テスト結果 (/tests)`;

const recommendedFlow = [
  "銘柄を選択（例: 7203.T トヨタ）",
  "「データ取込」→ 件数 N本 (yahoo) と表示されることを確認",
  "ECharts / Chart.js に価格線が出ることを確認",
  "「ファンダ」「ニュース」でファンダ・センチメントを取得",
  "「ML予測」「DL(LSTM)」で方向性を確認",
  "必要なら「バックテスト」「RAG質問」→「フルパイプライン」",
] as const;

const chartTips = [
  "テクニカルが空のときは先に「データ取込」（0件なら外部配信遮断の可能性）",
  "TradingView は TSE:7203 形式。ウィジェット非対応の場合は TV 本体で確認",
  "チャート更新後も空なら「更新」または再デプロイ後に再取込",
] as const;

const steps = [
  {
    title: "0. 最短フロー（画面操作）",
    body: "ダッシュボードのボタンだけで、取込→分析→予測まで一通り確認できます。",
    items: [...recommendedFlow],
  },
  {
    title: "1. 銘柄とモード確認",
    body: "ヘッダーの API ステータスと trading mode を確認します。",
    items: [
      "API ok / mode: paper を確認（本番売買キー未設定時は paper）",
      "銘柄セレクトで対象ティッカーを選択",
      "「更新」で最新の予測・注文・リスクを再取得",
    ],
  },
  {
    title: "2. 価格データ取込",
    body: "テクニカル・ML・DL・バックテストの前提となる OHLCV を DB に入れます。",
    items: [
      "「データ取込」を押す",
      "成功例: データ取込完了: 120本 (yahoo)",
      "0件の場合はエラー表示 → 再デプロイ / 別プロバイダキーを確認",
      "自動取込: /technical 呼び出し時にも不足分を補完",
    ],
  },
  {
    title: "3. テクニカル・チャート",
    body: "指標スナップショットと系列チャートを確認します。",
    items: [
      "左パネル: Trend / RSI / MACD / ADX / ATR",
      "ECharts: 価格 · ボリンジャー · RSI",
      "Chart.js: Close · SMA20",
      "TradingView: 外部チャート（埋め込み不可時は TV サイトへ）",
    ],
  },
  {
    title: "4. ファンダ・ニュース",
    body: "ファンダメンタルとニュース LLM 分析を取得します。",
    items: [
      "「ファンダ」→ PER / PBR / ROE など",
      "「ニュース」→ 日経・ロイター等の収集とセンチメント",
      "LLM キー未設定時はヒューリスティックにフォールバック",
    ],
  },
  {
    title: "5. ML / DL 予測",
    body: "機械学習・深層学習モデルで短期方向を推定します。",
    items: [
      "「ML予測」→ sklearn / XGBoost 等の合意シグナル",
      "「DL(LSTM)」→ LSTM（GRU / Transformer / TFT も API 可）",
      "十分なバー本数が必要（取込後に実行）",
    ],
  },
  {
    title: "6. バックテスト・RAG・リスク",
    body: "戦略検証と知識検索、リスクイベントを確認します。",
    items: [
      "「バックテスト」→ Return / Sharpe / MaxDD · エクイティ曲線",
      "「RAG質問」→ ニュース等のベクトル検索回答",
      "ポジション / リスクパネルでイベントを確認",
    ],
  },
  {
    title: "7. フルパイプライン",
    body: "取込から分析・予測までを一括実行します。",
    items: [
      "緑の「フルパイプライン」を押す",
      "結果 JSON が画面下部に表示",
      "個別ボタンと同じ処理をまとめて走らせる想定",
    ],
  },
  {
    title: "8. テスト結果の確認",
    body: "pytest / Vitest の結果を Web で閲覧できます。",
    items: [
      "ヘッダー「テスト結果」または /tests/",
      "API: /api/v1/tests/summary · report · run",
      "ローカル: python scripts/run_tests.py",
    ],
  },
  {
    title: "9. 環境・デプロイメモ",
    body: "Railway / Docker での運用時の注意点です。",
    items: [
      "DATABASE_URL（asyncpg）· DATABASE_SSL_VERIFY=false（必要時）",
      "OPENAI_MODEL=gpt-4o-mini など利用可能モデルを指定",
      "健康確認: /api/v1/health/live",
      "Python 3.12 推奨（3.14 は依存で失敗しやすい）",
    ],
  },
] as const;

type Props = {
  open: boolean;
  onClose: () => void;
};

export function UsageGuidePanel({ open, onClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const [expanded, setExpanded] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const onHeaderPointerDown = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if ((e.target as HTMLElement).closest("[data-ug-toggle]")) return;
      if (!pos) return;
      dragRef.current = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        originX: pos.x,
        originY: pos.y,
      };
      setDragging(true);
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [pos],
  );

  const onHeaderPointerMove = useCallback((e: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    setPos({
      x: drag.originX + (e.clientX - drag.startX),
      y: drag.originY + (e.clientY - drag.startY),
    });
  }, []);

  const onHeaderPointerUp = useCallback((e: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    e.currentTarget.releasePointerCapture(e.pointerId);
  }, []);

  if (!open) return null;

  const style =
    pos != null
      ? ({
          position: "fixed" as const,
          left: pos.x,
          top: pos.y,
          right: "auto",
          bottom: "auto",
          width: "min(420px, calc(100vw - 2rem))",
          margin: 0,
        } as const)
      : undefined;

  return (
    <div
      ref={panelRef}
      className={`${styles.panel}${expanded ? "" : ` ${styles.collapsed}`}${dragging ? ` ${styles.dragging}` : ""}`}
      style={style}
      role="dialog"
      aria-label="利用手順"
      aria-modal="false"
    >
      <header
        className={styles.header}
        onPointerDown={(e) => {
          if (pos == null && panelRef.current) {
            const rect = panelRef.current.getBoundingClientRect();
            setPos({ x: rect.left, y: rect.top });
            dragRef.current = {
              pointerId: e.pointerId,
              startX: e.clientX,
              startY: e.clientY,
              originX: rect.left,
              originY: rect.top,
            };
            setDragging(true);
            e.currentTarget.setPointerCapture(e.pointerId);
            return;
          }
          onHeaderPointerDown(e);
        }}
        onPointerMove={onHeaderPointerMove}
        onPointerUp={onHeaderPointerUp}
        onPointerCancel={onHeaderPointerUp}
      >
        <div className={styles.headerText}>
          <span aria-hidden>☰</span>
          <div className={styles.headerTitles}>
            <strong>利用手順</strong>
            <span className={styles.headerSub}>Architecture &amp; Ops</span>
          </div>
          <span className={styles.dragHint}>ドラッグで移動</span>
        </div>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.toggle}
            data-ug-toggle
            aria-label={expanded ? "折りたたむ" : "開く"}
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "▼" : "▲"}
          </button>
          <button
            type="button"
            className={styles.closeBtn}
            data-ug-toggle
            aria-label="閉じる"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </header>

      {expanded ? (
        <div className={styles.body}>
          <div className={styles.hero}>
            <p className={styles.heroKicker}>Portfolio-ready demo</p>
            <h2 className={styles.heroTitle}>StockAI — 分析 · 予測 · 売買</h2>
            <p className={styles.heroLead}>
              データ取込からテクニカル / ファンダ / ニュースLLM / ML·DL / RAG / バックテスト /
              リスクまでを一つの画面で再現するワークフローです。
            </p>
            <div className={styles.stack} aria-label="Tech stack">
              {techStack.map((tag) => (
                <span key={tag} className={styles.stackPill}>
                  {tag}
                </span>
              ))}
            </div>
          </div>

          <section className={styles.featured} aria-label="パイプライン概要">
            <div className={styles.featuredHead}>
              <span className={styles.featuredBadge}>Architecture</span>
              <strong>エンドツーエンド・パイプライン</strong>
            </div>
            <p>
              銘柄選択 → OHLCV 取込 → テクニカル / ファンダ / ニュース → ML·DL 予測 → バックテスト · RAG ·
              リスク → 証券API（paper）までを一連で実行します。
            </p>
          </section>

          <section className={styles.featured} aria-label="推奨フロー">
            <div className={styles.featuredHead}>
              <span className={styles.featuredBadge}>Recommended</span>
              <strong>最短・安全な進め方</strong>
            </div>
            <p>
              まず「データ取込」でバー本数を確保してから、チャートと予測ボタンを順に実行してください。件数 0
              のまま先に進むとテクニカルが空のままになります。
            </p>
            <ul className={styles.items}>
              {recommendedFlow.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>

          <section className={styles.featured} aria-label="チャート注意">
            <div className={styles.featuredHead}>
              <span className={styles.featuredBadge}>Charts</span>
              <strong>チャートが表示されないとき</strong>
            </div>
            <ul className={styles.items}>
              {chartTips.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>

          <figure className={styles.diagram} aria-label="Service topology">
            <figcaption>Service topology</figcaption>
            <pre>{archDiagram}</pre>
          </figure>

          <p className={styles.scrollHint}>↓ セットアップから運用までの手順</p>

          <ol className={styles.steps}>
            {steps.map((step) => (
              <li key={step.title}>
                <strong>{step.title}</strong>
                <p>{step.body}</p>
                <ul className={styles.items}>
                  {step.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>

          <p className={styles.footer}>
            ▼▲ で開閉 · ドラッグで移動 · × で閉じる · テストは /tests · 取込件数を必ず確認
          </p>
        </div>
      ) : null}
    </div>
  );
}
