# StockAI Agent Platform

株価予測・SNS運用自動化の AI エージェント基盤です。  
**データ収集 → 分析 → 予測 → 売買判断 → 自動発注（既定: ペーパー） → リスク管理 → 運用監視 → SNS下書き** を一連のパイプラインとして実装しています。

## 技術スタック

| 層 | 技術 |
|---|---|
| Backend | Python 3.12 / FastAPI / SQLAlchemy / Celery |
| DB | PostgreSQL 16 |
| Cache / Queue | Redis 7 |
| Frontend | Next.js 15 / React 19 / TypeScript |
| Infra | Docker Compose |

## アーキテクチャ

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Next.js UI │────▶│  FastAPI API │────▶│ PostgreSQL  │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────▼───────┐
                    │ Celery+Redis │  定期取込 / ウォッチリスト実行
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │ Market Data Providers   │
              │ Yahoo / AV / Polygon /  │
              │ Finnhub / Twelve Data   │
              │ (+ JPX/QUICK/BB stubs)  │
              └─────────────────────────┘
```

## 収集対象データ

- 株価・出来高（OHLCV）
- 板情報（order book）※商用フィード接続時
- 約定履歴（ticks）※商用フィード接続時
- 信用残・空売り残高（`margin_short` テーブル / 手動・商用投入）
- 為替・金利・原油・VIX・日経・TOPIX・S&P500・NASDAQ（マクロ系列）

## 推奨 API

| 用途 | プロバイダ | 備考 |
|---|---|---|
| 研究・プロトタイプ | Yahoo Finance | キー不要（`yfinance`） |
| 汎用 | Alpha Vantage / Twelve Data / Finnhub | `.env` にキー設定 |
| 米国株高品質 | Polygon.io | |
| 国内機関 | JPX / QUICK / Bloomberg | `collectors/commercial.py` スタブ |

## クイックスタート

### 1. 環境変数

```bash
cp .env.example .env
# 必要に応じて API キーを記入
```

### 2. Docker 起動

```bash
docker compose up --build
```

| サービス | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API / Docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

### 3. パイプライン実行例

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"ticker":"7203.T","quantity":100}'
```

ダッシュボードの「フルパイプライン実行」でも同様です。

## ローカル開発（Docker なし）

### Backend

Python **3.11 または 3.12** を使用してください（3.14 は未対応）。

```bash
cd backend
py -3.12 -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
# PostgreSQL / Redis を起動したうえで
uvicorn app.main:app --reload --port 8000
```
### Frontend

```bash
cd frontend
npm install
npm run dev
```

## 主要 API

| Method | Path | 説明 |
|---|---|---|
| GET | `/api/v1/health` | ヘルス + プロバイダ状態 |
| POST | `/api/v1/ingest/bars` | OHLCV 取込 |
| POST | `/api/v1/ingest/macro` | マクロ指標取込 |
| POST | `/api/v1/predict` | 予測 |
| POST | `/api/v1/pipeline/run` | フルエージェント実行 |
| GET | `/api/v1/orders` | 注文一覧 |
| GET | `/api/v1/positions` | ポジション |
| GET | `/api/v1/risk/events` | リスクイベント |
| GET | `/api/v1/sns/posts` | SNS 下書き |

## リスク・運用上の注意

- 既定の `TRADING_MODE=paper` です。実発注はブローカー接続実装後にのみ有効化してください。
- 日次損失上限・ポジション比率・注文金額上限は `.env` の `MAX_*` で制御します。
- 本システムは研究・開発用途の骨格です。投資判断の最終責任は利用者にあります。

## ディレクトリ構成

```
StockPricePpredictionTool/
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── agents/pipeline.py      # 統合エージェント
│   │   ├── collectors/             # マーケットデータ取得
│   │   ├── services/               # 取込・予測・売買・SNS
│   │   ├── workers/                # Celery 定期ジョブ
│   │   └── api/routes.py
│   └── db/init.sql
└── frontend/                       # Next.js ダッシュボード
```
"# StockPricePpredictionTool-" 
