-- 量化交易系统数据库初始化
-- PostgreSQL 16+
-- 数据库: quant_db  用户: zhongxin  端口: 5432

-- CREATE DATABASE quant_db ENCODING 'UTF8';

-- ============================================================
-- 1. 股票基本信息
-- ============================================================
CREATE TABLE stock_info (
    code        VARCHAR(10) PRIMARY KEY,
    name        VARCHAR(20),
    market      VARCHAR(4),                -- sh/sz
    board       VARCHAR(4),                -- main/sme/gem
    status      SMALLINT DEFAULT 1,        -- 1=正常 0=退市
    updated_at  TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE stock_info IS '股票基本信息';

-- ============================================================
-- 2. 日K线
-- ============================================================
CREATE TABLE kline_daily (
    code        VARCHAR(10) NOT NULL,
    date        DATE NOT NULL,
    open        DECIMAL(12,4),
    high        DECIMAL(12,4),
    low         DECIMAL(12,4),
    close       DECIMAL(12,4),
    volume      BIGINT,
    amount      DECIMAL(18,2),
    PRIMARY KEY (code, date)
);

CREATE INDEX idx_kline_daily_date ON kline_daily(date);
CREATE INDEX idx_kline_daily_code_date_desc ON kline_daily(code, date DESC);

COMMENT ON TABLE kline_daily IS '日K线数据(前复权)';

-- ============================================================
-- 3. 30分钟K线
-- ============================================================
CREATE TABLE kline_30m (
    code        VARCHAR(10) NOT NULL,
    datetime    TIMESTAMP NOT NULL,
    open        DECIMAL(12,4),
    high        DECIMAL(12,4),
    low         DECIMAL(12,4),
    close       DECIMAL(12,4),
    volume      BIGINT,
    PRIMARY KEY (code, datetime)
);

CREATE INDEX idx_kline_30m_datetime ON kline_30m(datetime);
CREATE INDEX idx_kline_30m_code_dt_desc ON kline_30m(code, datetime DESC);

COMMENT ON TABLE kline_30m IS '30分钟K线数据';

-- ============================================================
-- 4. 自选股
-- ============================================================
CREATE TABLE watchlist (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(10) NOT NULL,
    group_name  VARCHAR(20) DEFAULT 'manual',
    add_date    DATE DEFAULT CURRENT_DATE,
    tags        TEXT[],
    reason      TEXT,
    pressure_at_add DECIMAL(12,4),
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE(code, group_name)
);

CREATE INDEX idx_watchlist_group ON watchlist(group_name);
CREATE INDEX idx_watchlist_code ON watchlist(code);

COMMENT ON TABLE watchlist IS '自选股(auto=自动选入, manual=手动添加)';

-- ============================================================
-- 5. 交易信号记录
-- ============================================================
CREATE TABLE signal_log (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(10) NOT NULL,
    signal_name VARCHAR(30),
    signal_type VARCHAR(10),               -- buy/sell
    close_price DECIMAL(12,4),
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_signal_log_created ON signal_log(created_at);
CREATE INDEX idx_signal_log_code_date ON signal_log(code, created_at DESC);
CREATE INDEX idx_signal_log_dedup ON signal_log(code, signal_name, (created_at::date));

COMMENT ON TABLE signal_log IS '交易信号记录';

-- ============================================================
-- 6. 回测记录
-- ============================================================
CREATE TABLE backtest_log (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(10),
    strategy        VARCHAR(30),
    total_return    DECIMAL(8,2),
    annual_return   DECIMAL(8,2),
    max_drawdown    DECIMAL(8,2),
    sharpe_ratio    DECIMAL(8,2),
    win_rate        DECIMAL(8,2),
    profit_loss_ratio DECIMAL(8,2),
    total_trades    INT,
    benchmark_return DECIMAL(8,2),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_backtest_log_code ON backtest_log(code, strategy);

COMMENT ON TABLE backtest_log IS '回测结果记录';
