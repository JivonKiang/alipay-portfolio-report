#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号状态机（移植自 etf-quant signal_monitor.py）
- MA10/MA30 金叉 + MACD柱>0 -> BUY（买入信号）
- 金叉后持有期 -> HOLDING
- 达到持有天数或止盈线 -> SELL_READY
- 之后 -> WAIT
- 持仓告警（移植自 etf-quant position_alert.py）: 结合费率管理器输出解锁/卖出提醒

净值数据源: 天天基金 f10 API，当日缓存 cache/nav_cache/{code}.json
"""
import json
import os
import time
import urllib.request
from datetime import datetime, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SCRIPT_DIR, "cache", "nav_cache")

# 策略参数（对齐 etf-quant 回测: 胜率63-66%）
STRATEGY = {
    "fast": 10,
    "slow": 30,
    "hold_days": 20,
    "take_profit": 0.15,
}


def _cache_path(code):
    return os.path.join(CACHE_DIR, f"{code}.json")


def _fetch_nav_pingzhong(code):
    """天天基金 pingzhongdata 全量净值历史（升序 [{date, nav}]）"""
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                               "Referer": "http://fund.eastmoney.com/"})
    import re
    with urllib.request.urlopen(req, timeout=15) as resp:
        txt = resp.read().decode("utf-8", "ignore")
    m = re.search(r"Data_netWorthTrend\s*=\s*(\[.*?\]);", txt)
    if not m:
        return []
    raw = json.loads(m.group(1))
    rows = [{"date": datetime.fromtimestamp(x["x"] / 1000).date().isoformat(), "nav": x["y"]}
            for x in raw if x.get("y")]
    rows.sort(key=lambda r: r["date"])
    return rows


def _fetch_nav_f10(code, days=120):
    """f10 API 兜底（有pageSize上限，翻两页）"""
    rows = []
    for page in (1, 2):
        url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex={page}&pageSize={days}"
        headers = {"Referer": "https://fund.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())
                lst = data.get("Data", {}).get("LSJZList") or []
                rows += [{"date": r["FSRQ"], "nav": float(r["DWJZ"])}
                         for r in lst if r.get("DWJZ")]
                break
            except Exception:
                time.sleep(1)
    rows = {r["date"]: r["nav"] for r in rows}
    return [{"date": d, "nav": v} for d, v in sorted(rows.items())]


def fetch_nav_history(code, days=120):
    """
    获取基金净值历史（升序 [{date, nav}]）。
    当日已缓存直接读缓存，否则请求天天基金并落盘。失败隔离：返回 []。
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = _cache_path(code)
    today = date.today().isoformat()

    if os.path.exists(cache):
        try:
            with open(cache, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("date") == today and len(cached.get("rows") or []) >= days:
                return cached["rows"]
        except (OSError, json.JSONDecodeError):
            pass

    rows = []
    for fetcher in (_fetch_nav_pingzhong, _fetch_nav_f10):
        try:
            rows = fetcher(code)
            if rows:
                break
        except Exception:
            continue

    if rows:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({"date": today, "rows": rows}, f, ensure_ascii=False)
    return rows


# ===================== 指标计算 =====================

def ma_series(values, n):
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema_series(values, n):
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def macd_hist_series(values):
    """MACD柱 = 2*(DIF-DEA)，DIF=EMA12-EMA26，DEA=EMA9(DIF)"""
    e12 = ema_series(values, 12)
    e26 = ema_series(values, 26)
    dif = [e12[i] - e26[i] for i in range(len(values))]
    dea = ema_series(dif, 9)
    return [2 * (dif[i] - dea[i]) for i in range(len(values))]


# ===================== 状态机 =====================

def state_of(nav_rows, strategy=None):
    """
    返回 (state, detail)。state: BUY / HOLDING / SELL_READY / WAIT
    """
    st = {**STRATEGY, **(strategy or {})}
    navs = [r["nav"] for r in nav_rows]
    dates = [r["date"] for r in nav_rows]
    if len(navs) < st["slow"] + 2:
        return "WAIT", {"note": "净值数据不足"}

    mf = ma_series(navs, st["fast"])
    ms = ma_series(navs, st["slow"])
    hist = macd_hist_series(navs)

    # 从最近往回找最近一次金叉（MA fast 上穿 slow 且 MACD柱>0）
    buy_idx = None
    for i in range(len(navs) - 1, st["slow"] - 1, -1):
        if None in (mf[i], ms[i], mf[i - 1], ms[i - 1]):
            continue
        if mf[i - 1] <= ms[i - 1] and mf[i] > ms[i] and hist[i] > 0:
            buy_idx = i
            break
    if buy_idx is None:
        return "WAIT", {"note": "近期无金叉信号"}

    buy_date = dates[buy_idx]
    held = (date.today() - date.fromisoformat(buy_date)).days
    detail = {
        "buy_date": buy_date,
        "held_days": held,
        "buy_nav": navs[buy_idx],
        "latest_nav": navs[-1],
        "latest_date": dates[-1],
        "ret": round(navs[-1] / navs[buy_idx] - 1, 4),
    }
    if buy_idx == len(navs) - 1:
        return "BUY", detail                       # 最新净值日刚金叉
    if held < st["hold_days"]:
        if st.get("take_profit") and detail["ret"] >= st["take_profit"]:
            detail["reason"] = "止盈"
            return "SELL_READY", detail            # 持有期内达止盈线
        return "HOLDING", detail
    if held == st["hold_days"]:
        detail["reason"] = "满期"
        return "SELL_READY", detail                # 今日满期可卖出
    return "WAIT", detail                          # 已了结，等下一次金叉


def check_funds(funds, strategy=None):
    """
    funds: [{code, name}] -> rows [{code,name,state,...}]
    单只失败不影响其它（失败隔离，移植自 etf-quant-auto data_fetcher）
    """
    rows = []
    for f in funds:
        code, name = f["code"], f.get("name", "")
        try:
            nav_rows = fetch_nav_history(code)
            if not nav_rows:
                rows.append({"code": code, "name": name, "state": "ERROR", "note": "净值获取失败"})
                continue
            state, detail = state_of(nav_rows, strategy)
            rows.append({"code": code, "name": name, "state": state, **detail})
        except Exception as e:
            rows.append({"code": code, "name": name, "state": "ERROR", "note": str(e)})
    return rows


# ===================== 持仓告警（position_alert） =====================

def check_position_alerts(positions, fee_manager, states_by_code=None):
    """
    持仓级买卖提醒（移植自 etf-quant position_alert.py）
    positions: [{code/fund_code, name, entry_date, profit_rate?, ...}]
    fee_manager: fee_manager.FeeManager 实例
    states_by_code: check_funds() 结果按 code 索引，可选
    返回告警列表: 状态告警 + 费率解锁提醒
    """
    alerts = []
    for pos in positions or []:
        code = pos.get("code") or pos.get("fund_code", "")
        name = pos.get("name") or pos.get("fund_name", "")
        entry = pos.get("entry_date", "")
        days = fee_manager.days_held(entry) if entry else 0

        # 状态机告警
        st = (states_by_code or {}).get(code)
        if st:
            state = st.get("state")
            if state == "SELL_READY":
                alerts.append({
                    "fund_code": code, "fund_name": name, "type": "sell",
                    "severity": "warning",
                    "message": f"状态 SELL_READY（{st.get('reason', '满期')}），持有{st.get('held_days', days)}天，"
                               f"收益{st.get('ret', 0)*100:+.1f}%，考虑卖出",
                })
            elif state == "BUY":
                alerts.append({
                    "fund_code": code, "fund_name": name, "type": "buy",
                    "severity": "info",
                    "message": f"最新净值日出现MA金叉买入信号，可考虑加仓",
                })

        # 费率解锁提醒
        if entry:
            tier = fee_manager.get_fee_tier(days, code)
            if tier["severity"] == "BLOCK":
                alerts.append({
                    "fund_code": code, "fund_name": name, "type": "fee_block",
                    "severity": "danger",
                    "message": f"持有{days}天<{tier['lock_days']}天锁定期，赎回费{tier['fee_label']}，"
                               f"{tier['remaining_days']}天后({tier['unlock_date']})解锁",
                })
            elif tier["severity"] == "WARN":
                alerts.append({
                    "fund_code": code, "fund_name": name, "type": "fee_warn",
                    "severity": "warning",
                    "message": f"持有{days}天，赎回费{tier['fee_label']}，满30天后免赎回费",
                })
    return alerts


if __name__ == "__main__":
    funds = [{"code": "005844", "name": "东方人工智能主题混合C"},
             {"code": "006503", "name": "财通集成电路产业股票C"}]
    print("=== 信号状态机 ===")
    for r in check_funds(funds):
        print(f"  {r['name']}({r['code']}): {r['state']} {r.get('buy_date', r.get('note', ''))} "
              f"持有{r.get('held_days', '-')}天 收益{r.get('ret', 0)*100:+.1f}%")
