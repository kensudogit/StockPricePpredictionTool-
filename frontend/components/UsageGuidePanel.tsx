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
テクニカル / ファンダ / ニュース
    │ 統合分析 (ヒューリスティック)
    ▼
利益計画（OOS・手数料・トレンド関門）
    │
    ▼
本日の候補 / 日次評価
    │ 通過銘柄のみ
    ▼
Paper 発注評価 → 執行
    │
    ▼
値洗い（損切り・利確を実際に決済）`;

const recommendedFlow = [
  "「期待配分」で EV 上位だけにリスク予算を割る（全通過銘柄には張らない）",
  "配分銘柄をクリック → 期待円と推奨株数を確認して Paper 執行",
  "引け後「値洗い」→ +1R で建値防衛、その後トレール。利確/損切りは決済",
  "「実現損益」で机上 EV と実測（実現÷約定）を見比べる",
  "期待値は OOS の平均。利益は保証しない",
] as const;

const chartTips = [
  "テクニカルが空のときは先に「データ取込」（0件なら外部配信遮断の可能性）",
  "TradingView は TSE:7203 形式。ウィジェット非対応の場合は TV 本体で確認",
  "「更新」で更新完了メッセージが出ることを確認（反応がないときは再デプロイ）",
] as const;

const readinessScores = [
  "Paper 日常運用: ウォッチリストスキャン・利益関門・値洗い決済まで一通り可能",
  "Celery Beat: 9:15 スキャン / 16:20 日次（DAILY_AUTO_EXECUTE 既定 false）",
  "日本株 live: Alpaca + 確認語のみ。国内証券はスタブのまま拒否",
] as const;

const readinessDo = [
  "期待配分の上位だけに張る。通過銘柄を全部買わない",
  "利益関門を通過しない銘柄は見送る（それが正しい）",
  "WATCHLIST で見る銘柄を固定する（既定: 7203/6758/9984/8306/6501）",
  "mode: paper で通してから、Alpaca live を検討する",
] as const;

const readinessDont = [
  "国内証券（SBI/楽天/カブコム）への本番発注は未実装",
  "DAILY_AUTO_EXECUTE=true を確認なしで本番に付けない",
  "ML/DL の in-sample confidence を売買根拠にしない",
  "公開APIに認証なし → 本番キーを載せたまま無防備公開しない",
] as const;

const steps = [
  {
    title: "0. 最短フロー（画面操作）",
    body: "期待配分で上位だけに張り、値洗いで利を守り、実現損益で机上EVと実測を見ます。",
    items: [...recommendedFlow],
  },
  {
    title: "1. 銘柄とモード確認",
    body: "ヘッダーの API ステータスと trading mode を確認します。",
    items: [
      "API ok / mode: paper を確認（本番売買キー未設定時は paper）",
      "銘柄セレクトで対象ティッカーを選択",
      "「更新」→「更新完了（銘柄）」と出れば正常",
    ],
  },
  {
    title: "2. 価格データ取込",
    body: "テクニカル・ML・DL・バックテスト・売買の前提となる OHLCV を DB に入れます。",
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
    title: "4. ファンダ・ニュース・統合分析",
    body: "3領域を個別取得するか、「統合分析」で一括スコア化します。",
    items: [
      "「ファンダ」→ PER / PBR / ROE など",
      "「ニュース」→ 収集とセンチメント（銘柄特化は弱め）",
      "「統合分析」→ BUY/HOLD/SELL · レーダー · 根拠リスト",
      "重みの目安: Technical 45% / Fundamental 30% / News 25%（ヒューリスティック）",
    ],
  },
  {
    title: "5. ML / DL・予測精度（探索用）",
    body: "方向性の参考と、Walk-forward による正直な精度確認です。売買根拠にはしません。",
    items: [
      "「ML予測」→ 合意シグナル（毎回再学習・インサンプル信頼度に注意）",
      "「DL(LSTM)」→ 短期方向（データが少ないと過学習しやすい）",
      "「予測精度」→ Hit Rate / MAE · Pred vs Actual · Model vs Buy&Hold",
      "的中率が 50% 前後でも異常ではない（ランダムウォーク近傍）",
    ],
  },
  {
    title: "6. バックテスト・RAG",
    body: "既定は ols_signal（予測と同じ walk-forward）。SMA交差は探索用です。",
    items: [
      "「バックテスト」→ Strategy vs Buy&Hold / Drawdown",
      "手数料 5bps のみ・スリッページなし・単元未考慮",
      "「RAG質問」→ ニュース等の検索回答（埋め込みは簡易実装）",
    ],
  },
  {
    title: "7. Paper 売買（手動発注）",
    body: "売買パネルから模擬の買う/売るを実行し、注文・ポジションを記録します。",
    items: [
      "数量・ブローカー（通常 paper）・成行/指値を指定",
      "「買う」「売る」→ 約定メッセージと order_id を確認",
      "ポジション / リスク · シグナル / 注文パネルで反映を確認",
      "リスク前チェックあり。損切りの自動執行は未実装",
      "SBI/楽天/カブコムはスタブ（契約・実装後に接続）",
    ],
  },
  {
    title: "8. フルパイプライン・テスト",
    body: "一括実行と品質確認です。",
    items: [
      "緑の「フルパイプライン」→ 結果 JSON",
      "ヘッダー「テスト結果」または /tests/",
      "ローカル: python scripts/run_tests.py",
    ],
  },
  {
    title: "9. 実用性能の目安（2026-07 評価）",
    body: "コードレビューに基づくレディネスです。負荷実測ではありません。",
    items: [
      ...readinessScores,
      "Usable: 日次取込 · テクニカル · Walk-forward · Paper売買UI",
      "Prototype: ファンダ/ニュース/統合スコア/ML·DL/バックテスト",
      "Stub / 未着手: 国内証券 · 損切り自動執行 · API認証 · Railway定期実行",
    ],
  },
  {
    title: "10. 環境・デプロイメモ",
    body: "Railway / Docker での運用時の注意点です。",
    items: [
      "DATABASE_URL（asyncpg）· DATABASE_SSL_VERIFY=false（必要時）",
      "OPENAI_MODEL=gpt-4o-mini など利用可能モデルを指定",
      "健康確認: /api/v1/health/live",
      "Python 3.12 推奨（3.14 は依存で失敗しやすい）",
      "Railway は API 単体（Celery/Redis 定期ジョブはローカル Compose 向け）",
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
              データ取込からテクニカル / ファンダ / ニュース / 統合分析 / ML·DL / RAG / バックテスト /
              Paper売買までを一つの画面で再現するデモ向けワークフローです。実資金の日本株発注は未接続です。
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
              まず「データ取込」でバー本数を確保し、統合分析まで進めてから Paper
              記録します。ML/DL の数字は探索用で、売買根拠にはしません。
            </p>
            <ul className={styles.items}>
              {recommendedFlow.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>

          <section className={styles.featured} aria-label="実用性能">
            <div className={styles.featuredHead}>
              <span className={styles.featuredBadge}>Readiness</span>
              <strong>実用性能の目安（2026-07）</strong>
            </div>
            <p>
              Demo 74 / Paper日常 48 / 日本株本番 12（100点満点・静的レビュー）。当面は取込→分析→Paper記録まで。
            </p>
            <ul className={styles.items}>
              {readinessScores.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <p>
              <strong>やってよいこと</strong>
            </p>
            <ul className={styles.items}>
              {readinessDo.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <p>
              <strong>やらないこと</strong>
            </p>
            <ul className={styles.items}>
              {readinessDont.map((item) => (
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
            ▼▲ で開閉 · ドラッグで移動 · × で閉じる · 常用は取込→統合分析→Paper · ML/DLは探索用 · 本番日本株は未接続
          </p>
        </div>
      ) : null}
    </div>
  );
}
