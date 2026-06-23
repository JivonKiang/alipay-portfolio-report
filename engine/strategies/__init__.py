"""
策略引擎模块
包含：策略基类、MA60-120双均线、海龟通道、动量策略
"""
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from datetime import datetime


class Signal:
    """交易信号"""
    def __init__(self, code, signal_type, reason, nav, date):
        self.code = code
        self.signal_type = signal_type  # BUY / SELL / HOLD
        self.reason = reason
        self.nav = nav
        self.date = date

    def __repr__(self):
        return f"Signal({self.code}, {self.signal_type}, {self.reason}, {self.date})"


class BaseStrategy(ABC):
    """策略基类"""
    def __init__(self, name, params=None):
        self.name = name
        self.params = params or {}

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, code: str) -> list:
        """
        df 需包含列: nav_date, nav
        返回: list of Signal
        """
        pass


class MAStrategy(BaseStrategy):
    """MA双均线策略"""
    def __init__(self, params=None):
        super().__init__("MA", params or {"fast": 60, "slow": 120})

    def generate_signals(self, df, code):
        fast = self.params["fast"]
        slow = self.params["slow"]
        
        df = df.copy()
        df["nav_date"] = pd.to_datetime(df["nav_date"])
        df = df.sort_values("nav_date")
        df["ma_fast"] = df["nav"].rolling(fast).mean()
        df["ma_slow"] = df["nav"].rolling(slow).mean()
        df["signal"] = 0
        df.loc[df["ma_fast"] > df["ma_slow"], "signal"] = 1
        df.loc[df["ma_fast"] <= df["ma_slow"], "signal"] = -1
        df["signal_change"] = df["signal"].diff()
        
        signals = []
        for _, row in df.iterrows():
            if pd.isna(row["signal_change"]):
                continue
            if row["signal_change"] == 2:
                signals.append(Signal(
                    code, "BUY",
                    f"MA{fast}上穿MA{slow}",
                    row["nav"], row["nav_date"]
                ))
            elif row["signal_change"] == -2:
                signals.append(Signal(
                    code, "SELL",
                    f"MA{fast}下穿MA{slow}",
                    row["nav"], row["nav_date"]
                ))
        return signals


class TurtleStrategy(BaseStrategy):
    """海龟通道突破策略（简化版）"""
    def __init__(self, params=None):
        super().__init__("Turtle", params or {"entry": 55, "exit": 20})

    def generate_signals(self, df, code):
        entry_period = self.params["entry"]
        exit_period = self.params["exit"]
        
        df = df.copy()
        df["nav_date"] = pd.to_datetime(df["nav_date"])
        df = df.sort_values("nav_date")
        
        # entry: 突破过去entry天最高价 -> BUY
        # exit: 跌破过去exit天最低价 -> SELL
        df["high_entry"] = df["nav"].rolling(entry_period).max()
        df["low_exit"] = df["nav"].rolling(exit_period).min()
        
        df["signal"] = 0  # 0=空仓, 1=持仓
        in_position = False
        
        signals = []
        for i, row in df.iterrows():
            if i < max(entry_period, exit_period):
                continue
            
            if not in_position and row["nav"] >= row["high_entry"]:
                in_position = True
                signals.append(Signal(
                    code, "BUY",
                    f"突破{entry_period}日高点{row['high_entry']:.4f}",
                    row["nav"], row["nav_date"]
                ))
            elif in_position and row["nav"] <= row["low_exit"]:
                in_position = False
                signals.append(Signal(
                    code, "SELL",
                    f"跌破{exit_period}日低点{row['low_exit']:.4f}",
                    row["nav"], row["nav_date"]
                ))
        return signals


class MomentumStrategy(BaseStrategy):
    """动量策略：当近N日涨幅超过阈值时买入，跌破均线卖出"""
    def __init__(self, params=None):
        super().__init__("Momentum", params={"period": 60, "threshold": 0.05})

    def generate_signals(self, df, code):
        period = self.params["period"]
        threshold = self.params["threshold"]
        
        df = df.copy()
        df["nav_date"] = pd.to_datetime(df["nav_date"])
        df = df.sort_values("nav_date")
        df["momentum"] = df["nav"].pct_change(period)
        df["ma20"] = df["nav"].rolling(20).mean()
        
        df["signal"] = 0
        df.loc[df["momentum"] > threshold, "signal"] = 1
        df.loc[(df["signal"] == 1) & (df["nav"] < df["ma20"]), "signal"] = -1
        df["signal_change"] = df["signal"].diff()
        
        signals = []
        for _, row in df.iterrows():
            if pd.isna(row["signal_change"]):
                continue
            if row["signal_change"] == 2:
                signals.append(Signal(
                    code, "BUY",
                    f"{period}日动量{row['momentum']:.2%} > {threshold:.1%}",
                    row["nav"], row["nav_date"]
                ))
        return signals


# 策略工厂
STRATEGY_MAP = {
    "MA60-120": lambda: MAStrategy({"fast": 60, "slow": 120}),
    "Turtle-55-20": lambda: TurtleStrategy({"entry": 55, "exit": 20}),
    "Momentum-60": lambda: MomentumStrategy({"period": 60, "threshold": 0.05}),
}


def get_strategy(name):
    """获取策略实例"""
    if name in STRATEGY_MAP:
        return STRATEGY_MAP[name]()
    raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_MAP.keys())}")
