"""
决策引擎 - 每日运行，生成交易信号并推送到通知模块
"""
import sys
import os
import json
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
from data.database import get_conn
from engine.strategies import get_strategy
from engine.backtest import BacktestEngine
from fee.fee_model import is_trade_worthwhile


class DecisionEngine:
    def __init__(self):
        self.strategies = ["MA60-120", "Turtle-55-20"]
        self.primary_strategy = "MA60-120"

    def get_enabled_funds(self):
        """获取启用的基金列表"""
        conn = get_conn()
        rows = conn.execute("SELECT code, name, fund_type FROM fund_info WHERE enabled=1").fetchall()
        conn.close()
        return [{"code": r[0], "name": r[1], "type": r[2]} for r in rows]

    def get_latest_signals(self):
        """获取所有基金的最新信号"""
        signals = []
        backtest = BacktestEngine()

        for fund in self.get_enabled_funds():
            code = fund["code"]
            name = fund["name"]

            df = backtest.load_data(code)
            if df.empty:
                continue

            for strategy_name in self.strategies:
                strategy = get_strategy(strategy_name)
                sigs = strategy.generate_signals(df, code)
                # 取最近的一个信号
                if sigs:
                    latest = sigs[-1]
                    latest_date = latest.date
                    if isinstance(latest_date, pd.Timestamp):
                        latest_date = latest_date.date()

                    signals.append({
                        "code": code,
                        "name": name,
                        "strategy": strategy_name,
                        "signal_type": latest.signal_type,
                        "reason": latest.reason,
                        "nav": latest.nav,
                        "date": latest_date,
                        "is_primary": strategy_name == self.primary_strategy,
                    })

        return signals

    def should_trade(self, signal, current_holdings=None):
        """判断信号是否应该执行（考虑费用过滤和持仓）"""
        # 检查是否已有持仓
        if current_holdings:
            for holding in current_holdings:
                if holding["code"] == signal["code"] and holding["status"] == "HOLDING":
                    if signal["signal_type"] == "BUY":
                        return False, "已持仓，不重复买入"

        # 费用过滤（仅对BUY信号）
        if signal["signal_type"] == "BUY":
            # 基于历史回测的平均收益来判断
            hold_days = 365  # 默认假设持有1年
            expected_return = 10  # 默认预期10%年化
            ok, msg = is_trade_worthwhile(expected_return, hold_days)
            return ok, msg

        return True, "通过"

    def save_signal(self, signal, executed=False):
        """保存信号到数据库"""
        conn = get_conn()
        date_val = signal["date"]
        if isinstance(date_val, pd.Timestamp):
            date_val = date_val.strftime("%Y-%m-%d")
        elif isinstance(date_val, datetime):
            date_val = date_val.strftime("%Y-%m-%d")

        conn.execute(
            """INSERT OR IGNORE INTO signal_log 
            (code, signal_type, strategy, nav, reason, signal_date, executed) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (signal["code"], signal["signal_type"], signal["strategy"],
             signal["nav"], signal["reason"], date_val, 1 if executed else 0),
        )
        conn.commit()
        conn.close()

    def daily_run(self, save_signals=True):
        """每日运行决策引擎"""
        signals = self.get_latest_signals()

        # 获取当前持仓
        conn = get_conn()
        holdings = []
        for row in conn.execute("SELECT code, shares, status FROM position WHERE status='HOLDING'").fetchall():
            holdings.append({"code": row[0], "shares": row[1], "status": row[2]})
        conn.close()

        decisions = []
        for sig in signals:
            should_exec, reason = self.should_trade(sig, holdings)
            sig["should_execute"] = should_exec
            sig["filter_reason"] = reason
            decisions.append(sig)

            if save_signals:
                self.save_signal(sig, should_exec)

        return decisions

    def format_report(self, decisions):
        """Format decision report as readable markdown"""
        if not decisions:
            return "No trading signals today."

        lines = ["## Fund Trend Trading Decision Report", f"Date: {date.today()}", ""]

        buy_signals = [d for d in decisions if d["signal_type"] == "BUY"]
        sell_signals = [d for d in decisions if d["signal_type"] == "SELL"]

        if buy_signals:
            lines.append("### BUY Signals")
            for s in buy_signals:
                flag = "EXECUTE" if s["should_execute"] else f"SKIP ({s['filter_reason']})"
                lines.append(f"- {s['name']}({s['code']}) [{s['strategy']}] {flag}")
                lines.append(f"  Reason: {s['reason']} | NAV: {s['nav']:.4f} | Date: {s['date']}")

        if sell_signals:
            lines.append("\n### SELL Signals")
            for s in sell_signals:
                flag = "SELL" if s["should_execute"] else f"SKIP ({s['filter_reason']})"
                lines.append(f"- {s['name']}({s['code']}) [{s['strategy']}] {flag}")
                lines.append(f"  Reason: {s['reason']} | NAV: {s['nav']:.4f} | Date: {s['date']}")

        lines.append(f"\nTotal: {len(buy_signals)} BUY signals, {len(sell_signals)} SELL signals.")
        return "\n".join(lines)
