# StockAI Agent Platform

株価予測・SNS運用自動化の AI エージェント基盤です。  
**データ収集 → テクニカル/ファンダ/ニュース分析 → ML・DL予測 → 売買判断 → 自動発注 → リスク管理 → バックテスト → RAG** を統合しています。

## 技術スタック

| 層 | 技術 |
|---|---|
| Backend | Python 3.12 / FastAPI / SQLAlchemy / Celery |
| DB | PostgreSQL 16 + **pgvector** |
| Cache / Queue | Redis 7 |
| ML | scikit-learn / XGBoost / LightGBM / CatBoost |
| DL | PyTorch（LSTM/GRU/Transformer/TFT）※ TensorFlow 任意 |
| Backtest | pandas / Backtrader / vectorbt（Zipline はアダプタ） |
| Frontend | Next.js 15 / React 19 / **ECharts / Chart.js / TradingView** |
| Infra | Docker Compose |

## 実装機能マップ

### ニュース分析
収集: 決算 / 適時開示・IR / 日経(proxy) / ロイター / Bloomberg(proxy) / SEC EDGAR / SNS  
LLM: OpenAI / Claude / Gemini（未設定時はヒューリスティック）  
API: `POST /api/v1/news/collect`, `POST /api/v1/news/analyze`, `POST /api/v1/news/{id}/enrich`

### テクニカル分析
トレンド（SMA/EMA/MACD/ADX）、オシレーター（RSI/Stoch/CCI）、ボラティリティ（ATR/BB）、出来高（VWAP/OBV）  
API: `GET /api/v1/technical/{ticker}`

### ファンダメンタル
PER / PBR / ROE / ROA / EPS / BPS / 営業利益率 / 自己資本比率  
API: `POST /api/v1/fundamentals/ingest`, `GET /api/v1/fundamentals/{ticker}`

### AI予測（証拠付き OLS が正本）
翌営業日価格・方向は `POST /api/v1/predict`（`ridge_ols_v1`）。  
毎回 **walk-forward OOS**（方向的中率・手数料込み戦略リターン）を `evidence` に載せる。  
`evidence.ok` が false ならシグナルは様子見。in-sample の confidence だけでは発注しない。

利益関門（`assess_edge` / `GET /api/v1/trading/plan/{ticker}`）は、手数料控除後の OOS 期待値・Sharpe・予測幅・トレンド一致が揃ったときだけ buy/sell する。数量はリスク予算×期待値スケールに Quarter-Kelly の上限を掛ける。利益は保証しない。

期待値の寄せ方:

- `POST /api/v1/trading/allocate` — ウォッチリストを EV×Sharpe×予測幅で順位付けし、日次リスク予算を上位 `MAX_NEW_TRADES_PER_DAY` 銘柄に割る
- `GET /api/v1/trading/expectancy` — 実現損益÷約定回数（机上 EV との差を見る）
- 値洗い時に +1R で損切りを建値へ、その後は高値（安値）から `TRAIL_STOP_PCT` で追随
- 自動発注は配分の上位だけ（全通過銘柄には張らない）

日次運用:

- `GET /api/v1/watchlist` / `POST /api/v1/trading/scan` — ウォッチリストを取込→計画
- `POST /api/v1/ops/mark` — 値洗い。損切り・利確に当たったら建玉を決済（利益関門は通さない）
- `POST /api/v1/ops/daily` — スキャン + 値洗い。新規発注は `DAILY_AUTO_EXECUTE=true` のときだけ
- Celery: 9:15 スキャン、16:20 日次（東京）
- 画面: 「本日の候補」「日次評価」「値洗い」

ML アンサンブル（`POST /api/v1/ml/predict`）と DL（`POST /api/v1/dl/predict`）は参考。  
`confidence` は in-sample。OOS は `oos` / `evidence_ok`。DL はライブ証拠に使わない。

### ベクトルDB / RAG
既定: **pgvector**（Pinecone / Weaviate / Milvus / Qdrant アダプタあり）  
保存: 決算・IR・ニュース・チャット  
API: `POST /api/v1/rag/ingest`, `POST /api/v1/rag/query`

### 自動売買（関門）
- 既定: `TRADING_MODE=paper` / `BROKER_NAME=paper`。paper は `PAPER_FEE_BPS` を約定値に乗せる。
- 評価: `POST /api/v1/trading/evaluate`（発注しない）
- 執行: `POST /api/v1/brokers/order` とパイプライン。どちらも `can_place` を通す。
- live は `LIVE_TRADING_CONFIRM=I_UNDERSTAND_LIVE_RISK` + 実装済み会場（Alpaca キー）のみ。
- SBI / 楽天 / カブコム / IBKR はスタブ。`place_order` は関門で拒否する。
- 準備状況: `GET /api/v1/trading/readiness`、`GET /api/v1/health` の `live_venue`

### バックテスト
既定戦略: **`ols_signal`**（予測と同じ walk-forward 方向）。SMA クロスは `strategy=sma_crossover`。  
API: `POST /api/v1/backtest/run`

### リスク管理（必須）
損切り / 利確 / ポジションサイズ / 最大損失 / 最大保有数 / レバレッジ  
API: `POST /api/v1/risk/position-size`, `POST /api/v1/risk/evaluate/{ticker}`  
値洗いでトリガーしたら `POST /api/v1/ops/mark` が建玉を決済する（決済は利益関門・クールダウンを通さない）。

## クイックスタート

```bash
cp .env.example .env
docker compose up --build
```

| URL | 用途 |
|---|---|
| http://localhost:3000 | ダッシュボード（ECharts / Chart.js / TradingView） |
| http://localhost:8000/docs | OpenAPI |

### クラウドデプロイ（Railway 等）

ルートの `Dockerfile` が **フロント（Next.js 静的書き出し）+ API** を1サービスでビルドします。

- `/` → StockAI ダッシュボード
- `/api/v1/*` → API
- `/docs` → OpenAPI
- ビルド時 `NEXT_PUBLIC_API_URL` は空（同一オリジンで `/api/v1` を呼ぶ）
- 必須環境変数: `DATABASE_URL`, `REDIS_URL`（任意）
- `DATABASE_URL` は Railway の `postgres://...` でも可（`postgresql+asyncpg://` へ自動変換）
- Healthcheck: `GET /api/v1/health`

> 既存の `postgres_data` ボリュームがある場合、pgvector イメージ切替のため  
> `docker compose down -v` でボリューム再作成が必要なことがあります。

### 例

```bash
# データ取込
curl -X POST http://localhost:8000/api/v1/ingest/bars \
  -H "Content-Type: application/json" -d '{"ticker":"7203.T","limit":200}'

# テクニカル
curl http://localhost:8000/api/v1/technical/7203.T

# バックテスト
curl -X POST http://localhost:8000/api/v1/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"ticker":"7203.T","engine":"pandas"}'

# ML アンサンブル
curl -X POST http://localhost:8000/api/v1/ml/predict \
  -H "Content-Type: application/json" -d '{"ticker":"7203.T"}'
```

## 環境変数（抜粋）

- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` — LLM
- `VECTOR_BACKEND=pgvector` — RAG バックエンド
- `ALPACA_API_KEY` / `SBI_API_KEY` / … — 証券 API
- `DEFAULT_STOP_LOSS_PCT` / `MAX_OPEN_POSITIONS` / `MAX_LEVERAGE` — リスク
- `LIVE_TRADING_CONFIRM` — live のみ `I_UNDERSTAND_LIVE_RISK`
- `PAPER_FEE_BPS` / `MIN_OOS_HIT_RATE` / `MIN_OOS_SAMPLES` — paper 手数料と予測ゲート

## ディレクトリ

```
backend/app/
  analysis/     # technical, fundamental, news
  llm/          # OpenAI / Claude / Gemini
  ml/           # sklearn / xgb / lgbm / catboost
  dl/           # LSTM GRU Transformer TFT
  rag/          # pgvector RAG
  brokers/      # SBI/楽天/カブコム/IBKR/Alpaca
  backtest/     # vectorbt / backtrader / pandas
  risk/         # 損切り・利確・サイジング
frontend/
  components/AnalysisCharts.tsx  # ECharts + Chart.js + TradingView
```

## テスト

```bash
# 依存関係
cd backend && pip install -r requirements.txt -r requirements-dev.txt
cd ../frontend && npm install

# 全テスト実行 → test-results/ に HTML/JSON 出力
python scripts/run_tests.py
```

Web で確認:
- ダッシュボードの「テスト結果」または `/tests/`
- `/api/v1/tests/summary`（JSON）
- `/api/v1/tests/report`（HTML）
- `/test-results/`（静的レポート）
- `POST /api/v1/tests/run?wait=true` で再実行

- 実発注は `TRADING_MODE=live` かつブローカー接続実装後のみ。
- 日経・Bloomberg の本番フィードはライセンスが必要（現状は公開 RSS / Google News proxy）。
- GPT-5.5 など最新モデル名は `.env` の `OPENAI_MODEL` で指定可能です。
