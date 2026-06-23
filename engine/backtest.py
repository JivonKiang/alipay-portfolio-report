"""
回测引擎 - 基于真实净值数据回测策略表现
支持多策略、多基金同时回测，考虑费用
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime
from data.database import get_conn
from engine.strategies import get_strategy
from fee.fee_model import calc_trade_cost, calc_net_return


class BacktestEngine:
    def __init__(self, initial_capital=100000, fee_mode="full"):
        """
        initial_capital: 初始资金
        fee_mode: "full" 含申购+赎回费, "buy_only" 仅申购费, "none" 无费用
        """
        self.initial_capital = initial_capital
        self.fee_mode = fee_mode
        self.results = {}

    def load_data(self, code):
        """从数据库加载基金净值数据"""
        conn = get_conn()
        query = """
            SELECT nav_date, nav 
            FROM fund_nav 
            WHERE code = ? 
            ORDER BY nav_date
        """
        df = pd.read_sql_query(query, conn, params=(code,))
        conn.close()
        df["nav_date"] = pd.to_datetime(df["nav_date"])
        return df

    def get_fund_name(self, code):
        conn = get_conn()
        row = conn.execute("SELECT name FROM fund_info WHERE code=?", (code,)).fetchone()
        conn.close()
        return row[0] if row else code

    def run_single(self, code, strategy_name, start_date=None, end_date=None):
        """
        对单只基金运行回测
        返回: dict {trades, metrics, df}
        """
        df = self.load_data(code)
        if df.empty:
            return None

        if start_date:
            df = df[df["nav_date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["nav_date"] <= pd.to_datetime(end_date)]

        strategy = get_strategy(strategy_name)
        signals = strategy.generate_signals(df, code)

        # 模拟交易
        trades = self._simulate_trades(signals, df, code)
        metrics = self._calc_metrics(trades, df, code)

        self.results[(code, strategy_name)] = {
            "code": code,
            "name": self.get_fund_name(code),
            "strategy": strategy_name,
            "trades": trades,
            "metrics": metrics,
            "df": df,
        }
        return self.results[(code, strategy_name)]

    def _simulate_trades(self, signals, df, code):
        trades = []
        in_position = False
        buy_signal = None

        for sig in signals:
            if sig.signal_type == "BUY" and not in_position:
                buy_signal = sig
                in_position = True
            elif sig.signal_type == "SELL" and in_position and buy_signal:
                trades.append({"buy": buy_signal, "sell": sig})
                buy_signal = None
                in_position = False

        # 如果回测结束仍持仓，以最后净值平仓
        if in_position and buy_signal:
            last_row = df.iloc[-1]
            from engine.strategies import Signal
            close_sig = Signal(code, "SELL", "回测结束平仓", last_row["nav"], last_row["nav_date"])
            trades.append({"buy": buy_signal, "sell": close_sig})

        return trades

    def _calc_metrics(self, trades, df, code):
        """计算策略回测指标"""
        if not trades:
            return {
                "total_return": 0, "total_return_pct": 0, "annual_return_pct": 0,
                "sharpe": 0, "max_drawdown_pct": 0, "win_rate": 0,
                "trade_count": 0, "total_fee": 0,
                "avg_return_pct": 0, "avg_hold_days": 0,
            }

        capital = self.initial_capital
        equity_curve = [capital]
        trade_results = []

        for t in trades:
            buy_nav = t["buy"].nav
            sell_nav = t["sell"].nav
            buy_date = t["buy"].date
            sell_date = t["sell"].date
            hold_days = max((sell_date - buy_date).days, 1)

            if self.fee_mode == "full":
                net_profit, net_pct, fee = calc_net_return(
                    buy_nav, sell_nav, capital, buy_date, sell_date
                )
            elif self.fee_mode == "buy_only":
                from fee.fee_model import BUY_FEE_RATE
                fee = capital * BUY_FEE_RATE
                shares = capital * (1 - BUY_FEE_RATE) / buy_nav
                sell_value = shares * sell_nav
                net_profit = sell_value - capital
                net_pct = (net_profit / capital) * 100
            else:
                fee = 0
                shares = capital / buy_nav
                sell_value = shares * sell_nav
                net_profit = sell_value - capital
                net_pct = net_profit / capital * 100

            capital += net_profit
            equity_curve.append(capital)
            trade_results.append({
                "hold_days": hold_days,
                "return_pct": net_pct,
                "fee": fee,
                "net_profit": net_profit,
            })

        equity_series = pd.Series(equity_curve)
        returns = equity_series.pct_change().dropna()

        # 年化收益率
        total_days = (df["nav_date"].max() - df["nav_date"].min()).days
        total_return_pct = ((capital - self.initial_capital) / self.initial_capital) * 100
        annual_return_pct = ((capital / self.initial_capital) ** (365 / max(total_days, 1)) - 1) * 100

        # 最大回撤
        peak = equity_series.expanding().max()
        drawdown = (equity_series - peak) / peak * 100
        max_drawdown_pct = drawdown.min()

        # 夏普比率
        sharpe = (returns.mean() / returns.std() * (252 ** 0.5)) if returns.std() > 0 else 0

        # 胜率
        wins = sum(1 for r in trade_results if r["return_pct"] > 0)
        win_rate = (wins / len(trade_results)) * 100 if trade_results else 0

        avg_return = np.mean([r["return_pct"] for r in trade_results])
        avg_hold = np.mean([r["hold_days"] for r in trade_results])
        total_fee = sum(r["fee"] for r in trade_results)

        return {
            "total_return": total_return_pct,
            "annual_return": annual_return_pct,
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_drawdown_pct, 2),
            "win_rate": round(win_rate, 1),
            "trade_count": len(trades),
            "total_fee": round(total_fee, 2),
            "avg_return": round(avg_return, 2),
            "avg_hold_days": round(avg_hold, 1),
        }

    def run_all(self, fund_codes, strategy_names, start_date=None, end_date=None):
        """多基金多策略批量回测"""
        all_results = []
        for code in fund_codes:
            for strategy_name in strategy_names:
                result = self.run_single(code, strategy_name, start_date, end_date)
                if result:
                    all_results.append(result)
        return all_results

    def summary_table(self):
        """生成回测汇总表"""
        rows = []
        for key, r in self.results.items():
            m = r["metrics"]
            rows.append({
                "基金": r["name"],
                "策略": r["strategy"],
                "交易次数": m["trade_count"],
                "总收益率(%)": round(m["total_return"], 2),
                "年化收益率(%)": round(m["annual_return"], 2),
                "最大回撤(%)": m["max_drawdown"],
                "夏普比率": m["sharpe"],
                "胜率(%)": m["win_rate"],
                "平均收益(%)": m["avg_return"],
                "平均持日": m["avg_hold_days"],
                "总费用(元)": m["total_fee"],
            })
        return pd.DataFrame(rows)
