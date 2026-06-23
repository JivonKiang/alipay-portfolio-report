"""
数据库初始化模块 - SQLite
创建基金净值表、交易记录表、信号日志表
"""
import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "fund_system.db")

SCHEMA_SQL = """
-- 基金基本信息表
CREATE TABLE IF NOT EXISTS fund_info (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    fund_type TEXT DEFAULT 'index',
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 基金日净值表
CREATE TABLE IF NOT EXISTS fund_nav (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    nav_date DATE NOT NULL,
    nav REAL NOT NULL,           -- 单位净值
    acc_nav REAL,                -- 累计净值
    daily_return REAL,           -- 日涨跌幅(%)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, nav_date)
);

CREATE INDEX IF NOT EXISTS idx_nav_code_date ON fund_nav(code, nav_date);

-- 交易记录表（手动记录支付宝实际操作）
CREATE TABLE IF NOT EXISTS trade_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    trade_type TEXT NOT NULL,    -- BUY / SELL
    amount REAL NOT NULL,        -- 交易金额
    nav REAL NOT NULL,           -- 成交净值
    shares REAL,                 -- 份额
    fee REAL DEFAULT 0,          -- 费用
    trade_date DATE NOT NULL,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 信号日志表
CREATE TABLE IF NOT EXISTS signal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    signal_type TEXT NOT NULL,   -- BUY / SELL / HOLD
    strategy TEXT NOT NULL,      -- 策略名称
    nav REAL,
    reason TEXT,                 -- 信号原因（如 MA60上穿MA120）
    signal_date DATE NOT NULL,
    executed INTEGER DEFAULT 0,  -- 是否已执行
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 持仓记录表
CREATE TABLE IF NOT EXISTS position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    shares REAL NOT NULL,
    cost_nav REAL NOT NULL,      -- 成本净值
    buy_date DATE NOT NULL,
    status TEXT DEFAULT 'HOLDING', -- HOLDING / CLOSED
    sell_date DATE,
    sell_nav REAL,
    profit REAL,
    profit_pct REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def init_db():
    """初始化数据库"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    return DB_PATH

def get_conn():
    """获取数据库连接"""
    return sqlite3.connect(DB_PATH)

if __name__ == "__main__":
    path = init_db()
    print(f"Database initialized: {path}")
