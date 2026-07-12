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

### AI予測（ML）
上昇率・下落率・売買判断のアンサンブル  
API: `POST /api/v1/ml/predict`

### 深層学習
LSTM / GRU / Transformer / TFT-lite（PyTorch）  
API: `POST /api/v1/dl/predict`

### ベクトルDB / RAG
既定: **pgvector**（Pinecone / Weaviate / Milvus / Qdrant アダプタあり）  
保存: 決算・IR・ニュース・チャット  
API: `POST /api/v1/rag/ingest`, `POST /api/v1/rag/query`

### 自動売買
日本: SBI / 楽天 / auカブコム（契約後接続スタブ）  
海外: Interactive Brokers / Alpaca  
既定: `TRADING_MODE=paper` / `BROKER_NAME=paper`  
API: `GET /api/v1/brokers`, `POST /api/v1/brokers/order`

### バックテスト（必須）
engines: `pandas` | `vectorbt` | `backtrader` | `zipline`(stub)  
API: `POST /api/v1/backtest/run`

### リスク管理（必須）
損切り / 利確 / ポジションサイズ / 最大損失 / 最大保有数 / レバレッジ  
API: `POST /api/v1/risk/position-size`, `POST /api/v1/risk/evaluate/{ticker}`

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
