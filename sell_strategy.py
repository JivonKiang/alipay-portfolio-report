#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
卖出策略引擎（移植自 nasdaq-dca sell-strategy.js，改造为 Python 服务端版）
- PE估值规则: PE分档触发 关注/减仓50%/减仓70%
- 收益率止盈规则: 持仓收益达到止盈线/强止盈线时告警
- 提醒持久化: 已忽略的提醒存 cache/sell_alerts_dismissed.json（对齐原 localStorage 方案）
- PE数据源: 蛋卷基金免费估值接口（失败时 PE 规则自动跳过）
"""
import json
import os
import urllib.request
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "cache")
DISMISSED_FILE = os.path.join(CACHE_DIR, "sell_alerts_dismissed.json")

# ===================== 默认规则 =====================
DEFAULT_RULES = {
    "pe_threshold": {
        "enabled": True,
        # A股宽基用 PE 百分位分档（0-1），更跨市场可比
        "pct_level1": 0.70,     # 百分位>70% 提示关注
        "pct_level2": 0.80,     # 百分位>80% 建议减仓
        "pct_level3": 0.90,     # 百分位>90% 强烈建议减仓
        "pe_level1": 35,        # 兜底: 百分位缺失时用绝对PE(适合纳指等)
        "pe_level2": 40,
        "pe_level3": 45,
        "reduce_percent1": 50,
        "reduce_percent2": 70,
    },
    "profit_threshold": {
        "enabled": True,
        "take_profit_rate": 0.20,       # 收益>20% 建议分批止盈
        "strong_take_profit_rate": 0.35, # 收益>35% 强烈建议止盈
        "reduce_percent": 100,
    },
}

# 蛋卷指数估值：返回主流宽基/行业指数 PE 与百分位
DJ_INDEX_EVA_URL = "https://danjuanfunds.com/djapi/index_eva/dj"
# 蛋卷代码 -> 展示名（只取本系统相关的宽基指数）
DJ_INDEXES = {
    "SH000300": "沪深300",
    "SH000905": "中证500",
    "SZ399006": "创业板指",
    "SH000016": "上证50",
    "SH000985": "中证全指",
}


def fetch_index_pe():
    """
    从蛋卷免费接口获取指数 PE。
    返回 {指数名: {"pe": float, "pe_percentile": float}}，失败返回 {}
    """
    result = {}
    try:
        req = urllib.request.Request(DJ_INDEX_EVA_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        for item in data.get("data", {}).get("items", []):
            name = DJ_INDEXES.get(item.get("index_code", ""))
            if not name:
                continue
            result[name] = {
                "pe": round(item.get("pe", 0), 2),
                "pe_percentile": round(item.get("pe_percentile", 0), 3),
            }
    except Exception:
        pass
    return result


def load_dismissed():
    try:
        with open(DISMISSED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def save_dismissed(dismissed):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(DISMISSED_FILE, "w", encoding="utf-8") as f:
        json.dump(dismissed, f, ensure_ascii=False, indent=2)


def dismiss_alert(alert_id):
    dismissed = load_dismissed()
    if alert_id not in dismissed:
        dismissed.append(alert_id)
        save_dismissed(dismissed)


def check_sell_signals(positions, rules=None, index_pe=None):
    """
    检查止盈/卖出信号（原 checkSellSignals 逻辑）
    positions: [{fund_code, fund_name, profit_rate, ...}]  profit_rate 为小数(0.2=20%)
    index_pe:  {指数名: {"pe":.., "pe_percentile":..}}，为 None 时自动拉取
    返回未忽略的告警列表
    """
    r = {**DEFAULT_RULES, **(rules or {})}
    alerts = []
    today = date.today().isoformat()

    # --- PE估值规则 ---
    if r["pe_threshold"]["enabled"]:
        if index_pe is None:
            index_pe = fetch_index_pe()
        pe_rule = r["pe_threshold"]
        for name, info in (index_pe or {}).items():
            pe = info.get("pe", 0)
            pct = info.get("pe_percentile", 0)
            if pe <= 0:
                continue
            # 优先用百分位分档，缺失时用绝对PE兜底
            if pct and 0 < pct < 1:
                hit = ("l3" if pct >= pe_rule["pct_level3"] else
                       "l2" if pct >= pe_rule["pct_level2"] else
                       "l1" if pct >= pe_rule["pct_level1"] else None)
                metric = f"PE={pe}（百分位{pct*100:.0f}%）"
            else:
                hit = ("l3" if pe >= pe_rule["pe_level3"] else
                       "l2" if pe >= pe_rule["pe_level2"] else
                       "l1" if pe >= pe_rule["pe_level1"] else None)
                metric = f"PE={pe}"
            if hit == "l3":
                alerts.append({
                    "id": f"pe_l3_{name}_{today}", "type": "pe",
                    "severity": "danger", "index": name,
                    "title": f"{name} 严重高估 — 强烈建议减仓",
                    "message": f"{name} {metric}，建议减仓 {pe_rule['reduce_percent2']}%",
                    "pe": pe, "reduce_percent": pe_rule["reduce_percent2"], "action": "reduce",
                })
            elif hit == "l2":
                alerts.append({
                    "id": f"pe_l2_{name}_{today}", "type": "pe",
                    "severity": "warning", "index": name,
                    "title": f"{name} 高估 — 建议减仓",
                    "message": f"{name} {metric}，建议减仓 {pe_rule['reduce_percent1']}%",
                    "pe": pe, "reduce_percent": pe_rule["reduce_percent1"], "action": "reduce",
                })
            elif hit == "l1":
                alerts.append({
                    "id": f"pe_l1_{name}_{today}", "type": "pe",
                    "severity": "info", "index": name,
                    "title": f"{name} 偏高 — 关注市场",
                    "message": f"{name} {metric}，做好减仓准备",
                    "pe": pe, "reduce_percent": 0, "action": "watch",
                })

    # --- 收益率止盈规则 ---
    if r["profit_threshold"]["enabled"]:
        p_rule = r["profit_threshold"]
        for pos in positions or []:
            rate = pos.get("profit_rate", 0)
            name = pos.get("fund_name") or pos.get("fund_code", "")
            code = pos.get("fund_code", "")
            if rate >= p_rule["strong_take_profit_rate"]:
                alerts.append({
                    "id": f"profit_strong_{code}_{today}", "type": "profit",
                    "severity": "danger", "fund_code": code,
                    "title": f"{name} 大额盈利 — 强烈建议止盈",
                    "message": f"收益率 {rate*100:+.1f}% 达强止盈线 {p_rule['strong_take_profit_rate']*100:.0f}%，建议止盈卖出 {p_rule['reduce_percent']}%",
                    "profit_rate": round(rate, 4), "reduce_percent": p_rule["reduce_percent"], "action": "sell",
                })
            elif rate >= p_rule["take_profit_rate"]:
                alerts.append({
                    "id": f"profit_{code}_{today}", "type": "profit",
                    "severity": "warning", "fund_code": code,
                    "title": f"{name} 达到止盈线 — 建议止盈",
                    "message": f"收益率 {rate*100:+.1f}% 达止盈线 {p_rule['take_profit_rate']*100:.0f}%，考虑分批止盈 50%",
                    "profit_rate": round(rate, 4), "reduce_percent": 50, "action": "sell",
                })

    dismissed = load_dismissed()
    return [a for a in alerts if a["id"] not in dismissed]


if __name__ == "__main__":
    print("=== 拉取指数PE（蛋卷） ===")
    pe = fetch_index_pe()
    for k, v in pe.items():
        print(f"  {k}: PE={v['pe']} 百分位={v['pe_percentile']*100:.1f}%")
    demo_positions = [
        {"fund_code": "005844", "fund_name": "东方人工智能C", "profit_rate": 0.22},
        {"fund_code": "006503", "fund_name": "财通集成电路C", "profit_rate": 0.05},
    ]
    print("\n=== 止盈检查 ===")
    for a in check_sell_signals(demo_positions, index_pe={}):
        print(f"  [{a['severity']}] {a['title']}: {a['message']}")
