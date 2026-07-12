-- StockAI initial schema
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Symbols / instruments
CREATE TABLE IF NOT EXISTS symbols (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(32) NOT NULL UNIQUE,
    name            VARCHAR(255),
    exchange        VARCHAR(64),
    asset_type      VARCHAR(32) NOT NULL DEFAULT 'equity',
    currency        VARCHAR(8) DEFAULT 'JPY',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- OHLCV bars
CREATE TABLE IF NOT EXISTS market_bars (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    timeframe       VARCHAR(16) NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    open            NUMERIC(18, 6) NOT NULL,
    high            NUMERIC(18, 6) NOT NULL,
    low             NUMERIC(18, 6) NOT NULL,
    close           NUMERIC(18, 6) NOT NULL,
    volume          NUMERIC(24, 4) DEFAULT 0,
    source          VARCHAR(32) NOT NULL,
    UNIQUE (symbol_id, timeframe, ts)
);
CREATE INDEX IF NOT EXISTS idx_market_bars_symbol_ts ON market_bars(symbol_id, ts DESC);

-- Order book snapshots
CREATE TABLE IF NOT EXISTS order_book_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    ts              TIMESTAMPTZ NOT NULL,
    bids            JSONB NOT NULL DEFAULT '[]',
    asks            JSONB NOT NULL DEFAULT '[]',
    source          VARCHAR(32) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_book_symbol_ts ON order_book_snapshots(symbol_id, ts DESC);

-- Trades (ticks)
CREATE TABLE IF NOT EXISTS trade_ticks (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    ts              TIMESTAMPTZ NOT NULL,
    price           NUMERIC(18, 6) NOT NULL,
    size            NUMERIC(18, 4) NOT NULL,
    side            VARCHAR(8),
    source          VARCHAR(32) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_ticks_symbol_ts ON trade_ticks(symbol_id, ts DESC);

-- Macro / index series (FX, rates, oil, VIX, Nikkei, TOPIX, S&P, NASDAQ)
CREATE TABLE IF NOT EXISTS macro_series (
    id              BIGSERIAL PRIMARY KEY,
    series_code     VARCHAR(64) NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    value           NUMERIC(18, 6) NOT NULL,
    source          VARCHAR(32) NOT NULL,
    UNIQUE (series_code, ts)
);
CREATE INDEX IF NOT EXISTS idx_macro_series_code_ts ON macro_series(series_code, ts DESC);

-- Margin / short interest (信用残・空売り残高)
CREATE TABLE IF NOT EXISTS margin_short (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    as_of_date      DATE NOT NULL,
    margin_buy      NUMERIC(24, 2),
    margin_sell     NUMERIC(24, 2),
    short_interest  NUMERIC(24, 2),
    source          VARCHAR(32) NOT NULL,
    UNIQUE (symbol_id, as_of_date, source)
);

-- Predictions
CREATE TABLE IF NOT EXISTS predictions (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    model_name      VARCHAR(64) NOT NULL,
    horizon         VARCHAR(16) NOT NULL,
    predicted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    target_ts       TIMESTAMPTZ,
    predicted_price NUMERIC(18, 6),
    direction       VARCHAR(8),
    confidence      NUMERIC(8, 4),
    features        JSONB DEFAULT '{}',
    meta            JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol ON predictions(symbol_id, predicted_at DESC);

-- Trading signals / decisions
CREATE TABLE IF NOT EXISTS trading_signals (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    signal_type     VARCHAR(16) NOT NULL,
    strength        NUMERIC(8, 4),
    rationale       TEXT,
    prediction_id   BIGINT REFERENCES predictions(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          VARCHAR(16) NOT NULL DEFAULT 'pending'
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    signal_id       BIGINT REFERENCES trading_signals(id),
    side            VARCHAR(8) NOT NULL,
    order_type      VARCHAR(16) NOT NULL DEFAULT 'market',
    quantity        NUMERIC(18, 4) NOT NULL,
    limit_price     NUMERIC(18, 6),
    status          VARCHAR(16) NOT NULL DEFAULT 'new',
    mode            VARCHAR(8) NOT NULL DEFAULT 'paper',
    broker_order_id VARCHAR(128),
    filled_qty      NUMERIC(18, 4) DEFAULT 0,
    avg_fill_price  NUMERIC(18, 6),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Positions
CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    quantity        NUMERIC(18, 4) NOT NULL DEFAULT 0,
    avg_cost        NUMERIC(18, 6),
    unrealized_pnl  NUMERIC(18, 6) DEFAULT 0,
    realized_pnl    NUMERIC(18, 6) DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol_id)
);

-- Risk events / circuit breakers
CREATE TABLE IF NOT EXISTS risk_events (
    id              BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(64) NOT NULL,
    severity        VARCHAR(16) NOT NULL,
    message         TEXT NOT NULL,
    details         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE
);

-- Portfolio snapshots for monitoring
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    equity          NUMERIC(18, 2) NOT NULL,
    cash            NUMERIC(18, 2) NOT NULL,
    exposure        NUMERIC(18, 2) NOT NULL,
    daily_pnl       NUMERIC(18, 2) NOT NULL,
    meta            JSONB DEFAULT '{}'
);

-- SNS posts / drafts
CREATE TABLE IF NOT EXISTS sns_posts (
    id              BIGSERIAL PRIMARY KEY,
    platform        VARCHAR(32) NOT NULL DEFAULT 'x',
    content         TEXT NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'draft',
    related_symbol  VARCHAR(32),
    scheduled_at    TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    external_id     VARCHAR(128),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Pipeline run log
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              BIGSERIAL PRIMARY KEY,
    stage           VARCHAR(32) NOT NULL,
    status          VARCHAR(16) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    details         JSONB DEFAULT '{}'
);

-- Seed common symbols / indices
INSERT INTO symbols (ticker, name, exchange, asset_type, currency) VALUES
    ('7203.T', 'Toyota Motor', 'TSE', 'equity', 'JPY'),
    ('6758.T', 'Sony Group', 'TSE', 'equity', 'JPY'),
    ('9984.T', 'SoftBank Group', 'TSE', 'equity', 'JPY'),
    ('^N225', 'Nikkei 225', 'INDEX', 'index', 'JPY'),
    ('^TOPX', 'TOPIX', 'INDEX', 'index', 'JPY'),
    ('^GSPC', 'S&P 500', 'INDEX', 'index', 'USD'),
    ('^IXIC', 'NASDAQ Composite', 'INDEX', 'index', 'USD'),
    ('^VIX', 'CBOE Volatility Index', 'INDEX', 'index', 'USD'),
    ('USDJPY=X', 'USD/JPY', 'FX', 'fx', 'JPY'),
    ('CL=F', 'Crude Oil WTI', 'CME', 'commodity', 'USD'),
    ('^TNX', 'US 10Y Treasury Yield', 'INDEX', 'rate', 'USD')
ON CONFLICT (ticker) DO NOTHING;

-- pgvector for RAG
CREATE EXTENSION IF NOT EXISTS vector;

-- News / disclosures
CREATE TABLE IF NOT EXISTS news_articles (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER REFERENCES symbols(id),
    source          VARCHAR(64) NOT NULL,
    category        VARCHAR(64) NOT NULL DEFAULT 'news',
    title           TEXT NOT NULL,
    url             TEXT,
    published_at    TIMESTAMPTZ,
    raw_text        TEXT,
    summary         TEXT,
    sentiment       NUMERIC(8, 4),
    sentiment_label VARCHAR(16),
    meta            JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_news_symbol ON news_articles(symbol_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_source ON news_articles(source, published_at DESC);

-- Fundamentals snapshots
CREATE TABLE IF NOT EXISTS fundamentals (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    as_of_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    per             NUMERIC(18, 6),
    pbr             NUMERIC(18, 6),
    roe             NUMERIC(18, 6),
    roa             NUMERIC(18, 6),
    eps             NUMERIC(18, 6),
    bps             NUMERIC(18, 6),
    operating_margin NUMERIC(18, 6),
    equity_ratio    NUMERIC(18, 6),
    market_cap      NUMERIC(24, 2),
    source          VARCHAR(32) NOT NULL DEFAULT 'yahoo',
    meta            JSONB DEFAULT '{}',
    UNIQUE (symbol_id, as_of_date, source)
);

-- Technical indicator snapshots (latest computed series tip)
CREATE TABLE IF NOT EXISTS technical_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    timeframe       VARCHAR(16) NOT NULL DEFAULT '1d',
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    indicators      JSONB NOT NULL DEFAULT '{}'
);

-- RAG document chunks
CREATE TABLE IF NOT EXISTS rag_documents (
    id              BIGSERIAL PRIMARY KEY,
    doc_type        VARCHAR(32) NOT NULL,
    symbol_id       INTEGER REFERENCES symbols(id),
    title           TEXT,
    content         TEXT NOT NULL,
    source_ref      VARCHAR(255),
    meta            JSONB DEFAULT '{}',
    embedding       vector(384),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rag_doc_type ON rag_documents(doc_type);

-- Chat history for RAG
CREATE TABLE IF NOT EXISTS chat_messages (
    id              BIGSERIAL PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,
    role            VARCHAR(16) NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, created_at);

-- Backtest runs
CREATE TABLE IF NOT EXISTS backtest_runs (
    id              BIGSERIAL PRIMARY KEY,
    ticker          VARCHAR(32) NOT NULL,
    strategy        VARCHAR(64) NOT NULL,
    engine          VARCHAR(32) NOT NULL,
    params          JSONB DEFAULT '{}',
    metrics         JSONB DEFAULT '{}',
    equity_curve    JSONB DEFAULT '[]',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

-- Risk policy / open risk orders
CREATE TABLE IF NOT EXISTS risk_orders (
    id              BIGSERIAL PRIMARY KEY,
    position_id     BIGINT REFERENCES positions(id),
    symbol_id       INTEGER NOT NULL REFERENCES symbols(id),
    order_kind      VARCHAR(16) NOT NULL,
    trigger_price   NUMERIC(18, 6) NOT NULL,
    quantity        NUMERIC(18, 4) NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    triggered_at    TIMESTAMPTZ
);

-- Enrich positions with risk fields (safe if already applied)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='positions' AND column_name='stop_loss') THEN
        ALTER TABLE positions ADD COLUMN stop_loss NUMERIC(18, 6);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='positions' AND column_name='take_profit') THEN
        ALTER TABLE positions ADD COLUMN take_profit NUMERIC(18, 6);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='positions' AND column_name='leverage') THEN
        ALTER TABLE positions ADD COLUMN leverage NUMERIC(8, 2) DEFAULT 1;
    END IF;
END $$;

