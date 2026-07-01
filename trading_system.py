#!/usr/bin/env python3
"""
五模块交易系统
整合 fund-trend-system 指数策略 + alipay-portfolio-report 快钱板块扫描

模块1: 市场环境判断 — 五大核心指数MA60/120趋势判定
模块2: 标的筛选 — 25个高波动板块扫描 + C类基金匹配 + 四道门控
模块3: 仓位管理 — 根据市场环境动态调整 20%-80%
模块4: 止盈止损 — 持仓盈亏监控 + 退出信号
模块5: 动态优化 — 信号历史 + 复盘数据

GitHub Actions 定时运行: 每天 11:00 / 14:30 (北京时间)
输出: output/trading_data.json + output/index.html (GitHub Pages)
"""
import json
import os
import sys
import urllib.request
import urllib.parse
import time
from datetime import datetime, date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
CACHE_DIR = os.path.join(SCRIPT_DIR, "cache")
TEMP_DIR = os.path.join(SCRIPT_DIR, "temp")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ===================== 配置 =====================
# 资金配置
TOTAL_FLEXIBLE = 96000   # 灵活资金
TOTAL_MONEY_FUND = 50000  # 货币基金
TOTAL_ASSETS = TOTAL_FLEXIBLE + TOTAL_MONEY_FUND

# 五大核心指数（东方财富代码）
INDEXES = {
    "上证50":     "1.000016",
    "沪深300":    "1.000300",
    "中证500":    "1.000905",
    "创业板指":   "1.399006",
    "科创50":     "1.000688",
}

# 板块（复用 quick_money 25个高波动板块）
BOARDS = {
    "科创芯片": "90.BK0990", "存储芯片": "90.BK1135", "半导体": "90.BK1036",
    "先进封装": "90.BK1032", "汽车芯片": "90.BK0962",
    "CPO": "90.BK1099", "光通信": "90.BK1098", "算力": "90.BK1134",
    "液冷服务器": "90.BK1156", "铜缆高速连接": "90.BK1168",
    "PCB": "90.BK0877", "AI手机": "90.BK1162", "智能穿戴": "90.BK0862",
    "消费电子": "90.BK0878", "AI眼镜": "90.BK1170",
    "固态电池": "90.BK0968", "低空经济": "90.BK1166", "人形机器人": "90.BK1158",
    "商业航天": "90.BK1161",
    "创新药": "90.BK0939", "稀土永磁": "90.BK0579", "数据要素": "90.BK1142",
    "量子科技": "90.BK1076", "脑机接口": "90.BK1124", "数字货币": "90.BK0903",
}

# C类基金匹配表（手动维护 + 自动搜索兜底）
FUND_MAP = {
    "科创芯片":  [("017560", "嘉实上证科创板芯片ETF联接C"), ("017560", "嘉实上证科创板芯片ETF联接C")],
    "半导体":    [("008888", "国联安中证半导体ETF联接C"), ("008282", "国泰CES半导体芯片ETF联接C")],
    "存储芯片":  [("008888", "国联安中证半导体ETF联接C")],
    "先进封装":  [("008888", "国联安中证半导体ETF联接C")],
    "汽车芯片":  [("008888", "国联安中证半导体ETF联接C")],
    "CPO":       [("017560", "嘉实上证科创板芯片ETF联接C")],
    "光通信":    [("017560", "嘉实上证科创板芯片ETF联接C")],
    "算力":      [("012629", "广发国证半导体芯片ETF联接C"), ("008888", "国联安中证半导体ETF联接C")],
    "液冷服务器": [("012629", "广发国证半导体芯片ETF联接C")],
    "铜缆高速连接": [("012629", "广发国证半导体芯片ETF联接C")],
    "PCB":       [("002256", "金信新能源汽车混合C"), ("008282", "国泰CES半导体芯片ETF联接C")],
    "AI手机":    [("008087", "华夏中证5G通信主题ETF联接C"), ("008282", "国泰CES半导体芯片ETF联接C")],
    "智能穿戴":  [("008282", "国泰CES半导体芯片ETF联接C")],
    "消费电子":  [("008282", "国泰CES半导体芯片ETF联接C"), ("002256", "金信新能源汽车混合C")],
    "AI眼镜":    [("008282", "国泰CES半导体芯片ETF联接C")],
    "固态电池":  [("014188", "华夏中证新能源汽车ETF联接C"), ("013049", "兴银中证科创创业50ETF联接C")],
    "低空经济":  [("002256", "金信新能源汽车混合C"), ("001643", "汇丰晋信智造先锋股票C")],
    "人形机器人": [("002256", "金信新能源汽车混合C"), ("001643", "汇丰晋信智造先锋股票C")],
    "商业航天":  [("001643", "汇丰晋信智造先锋股票C")],
    "创新药":    [("011179", "汇添富中证精准医疗C"), ("002708", "大摩健康产业混合C")],
    "稀土永磁":  [("011036", "嘉实中证稀土产业ETF联接C")],
    "数据要素":  [("008282", "国泰CES半导体芯片ETF联接C")],
    "量子科技":  [("012629", "广发国证半导体芯片ETF联接C")],
    "脑机接口":  [("002256", "金信新能源汽车混合C")],
    "数字货币":  [("008282", "国泰CES半导体芯片ETF联接C")],
}

# 策略参数
MA_FAST = 60
MA_SLOW = 120
STOP_LOSS_PCT = -0.08    # 止损线 -8%
TAKE_PROFIT_SHORT = 0.12  # 短线止盈 12%
TAKE_PROFIT_TREND = 0.18  # 趋势止盈 18%
SINGLE_MAX_RATIO = 0.30   # 单票上限 30%


# ===================== 数据获取 =====================

def fetch_eastmoney_kline(secid, count=120):
    """获取东方财富日K线数据"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=1&end=20500101&lmt={count}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if data.get("data") and data["data"].get("klines"):
            klines = []
            for line in data["data"]["klines"]:
                parts = line.split(",")
                klines.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]),
                })
            return klines
    except Exception as e:
        print(f"  [ERROR] fetch {secid}: {e}")
    return []


# ===================== 模块1: 市场环境判断 =====================

def calc_ma(values, period):
    """计算移动平均"""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def judge_market_environment():
    """
    基于五大核心指数的 MA60/MA120 位置判断市场环境。
    返回: (env_label, env_detail, total_position_ratio)
    """
    results = {}
    for name, code in INDEXES.items():
        klines = fetch_eastmoney_kline(code, count=150)
        if len(klines) < 120:
            results[name] = {"status": "data_insufficient"}
            continue

        closes = [k["close"] for k in klines]
        current = closes[-1]
        ma60 = calc_ma(closes, MA_FAST)
        ma120 = calc_ma(closes, MA_SLOW)

        # MA60 趋势方向
        if len(closes) >= 70:
            ma60_5d_ago = calc_ma(closes[:-5], MA_FAST)
            trend = "up" if ma60 > ma60_5d_ago else "down"
        else:
            trend = "flat"

        # 判断均线关系
        above_ma60 = current > ma60
        above_ma120 = current > ma120
        golden_cross = ma60 > ma120  # MA60在MA120上方（多头排列）

        if above_ma60 and above_ma120 and golden_cross and trend == "up":
            status = "bullish"
        elif (not above_ma60) and (not above_ma120):
            status = "bearish"
        elif above_ma60 and not above_ma120 and trend == "up":
            status = "recovering"
        elif above_ma120 and not above_ma60:
            status = "correcting"
        else:
            status = "neutral"

        results[name] = {
            "status": status,
            "current": round(current, 2),
            "ma60": round(ma60, 2) if ma60 else None,
            "ma120": round(ma120, 2) if ma120 else None,
            "above_ma60": above_ma60,
            "above_ma120": above_ma120,
            "golden_cross": golden_cross,
            "ma60_trend": trend,
        }

    # 综合判断
    statuses = [v.get("status") for v in results.values()]
    bullish_count = statuses.count("bullish") + statuses.count("recovering")
    bearish_count = statuses.count("bearish") + statuses.count("correcting")

    if bullish_count >= 4:
        env = "bull"
        env_cn = "牛市 — 敢重仓追龙头"
        position_ratio = 0.75
    elif bearish_count >= 4:
        env = "bear"
        env_cn = "熊市 — 清仓做反弹"
        position_ratio = 0.20
    elif bullish_count >= 3:
        env = "bull_lean"
        env_cn = "偏牛 — 积极做多"
        position_ratio = 0.60
    elif bearish_count >= 3:
        env = "bear_lean"
        env_cn = "偏熊 — 谨慎参与"
        position_ratio = 0.35
    else:
        env = "range"
        env_cn = "震荡市 — 快进快出赚差价"
        position_ratio = 0.45

    return {
        "environment": env,
        "environment_cn": env_cn,
        "total_position_ratio": position_ratio,
        "max_position_amount": round(TOTAL_FLEXIBLE * position_ratio),
        "index_details": results,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
    }


# ===================== 模块2: 标的筛选 =====================

def detect_board_signal(klines, board_name):
    """检测板块技术信号"""
    if len(klines) < 25:
        return None

    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    current = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else current

    change_pct = round((current - closes[-5]) / closes[-5] * 100, 2) if len(closes) >= 5 else 0
    today_change = round((current - prev_close) / prev_close * 100, 2)

    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, MA_FAST)

    # 量比
    avg_vol_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else volumes[-1]
    vol_ratio = round(volumes[-1] / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0

    signal = None

    # 信号1: MA60支撑反弹（缩量止跌）
    if ma60 and current > ma60:
        dist = (current - ma60) / ma60 * 100
        if 0 < dist < 3 and today_change > -1 and len(closes) >= 5:
            prev_5_change = (closes[-5] - closes[-10]) / closes[-10] * 100 if len(closes) >= 10 else 0
            if prev_5_change < -3:  # 之前跌过
                signal = {
                    "type": "dip_buy",
                    "label": "🔵 MA60支撑反弹",
                    "strength": "strong" if vol_ratio < 0.8 else "normal",
                    "reason": f"距MA60仅{dist:.1f}%，缩量止跌信号",
                }

    # 信号2: 放量突破MA20
    if not signal and ma20 and current > ma20 and today_change > 0:
        if vol_ratio > 1.3 and today_change > 1:
            prev_below = closes[-3] < ma20 if len(closes) >= 3 else False
            if prev_below:
                signal = {
                    "type": "breakout",
                    "label": "🟢 放量突破MA20",
                    "strength": "strong",
                    "reason": f"放量{vol_ratio:.1f}倍突破MA20",
                }

    # 信号3: 超跌反弹（距60日高点跌超15% + 今日止跌）
    if not signal and len(closes) >= 60:
        high_60 = max(closes[-60:])
        drop = (current - high_60) / high_60 * 100
        if drop < -15 and today_change > 0:
            signal = {
                "type": "oversold",
                "label": "🟡 超跌反弹",
                "strength": "weak",
                "reason": f"60日最大回撤{drop:.1f}%，今日反弹",
            }

    if signal:
        signal["board"] = board_name
        signal["change_pct"] = today_change
        signal["change_5d"] = change_pct
        signal["vol_ratio"] = vol_ratio
        signal["current"] = round(current, 2)
        signal["ma10"] = round(ma10, 1) if ma10 else None
        signal["ma20"] = round(ma20, 1) if ma20 else None
        signal["ma60"] = round(ma60, 1) if ma60 else None

    return signal


def match_funds(signal):
    """为信号匹配合适的C类基金"""
    board = signal["board"]
    if board in FUND_MAP:
        candidates = FUND_MAP[board]
        return [{"code": c[0], "name": c[1]} for c in candidates]
    return []


def purchase_gate(signal, fund_code, env):
    """
    四道门控：费率窗口 / 成本锚点 / 信号一致性 / 仓位上限
    """
    gates = []

    # 门控1: 成本锚点（涨幅>3%不追）
    change_pct = signal.get("change_pct", 0)
    env_label = env["environment"]
    threshold = 5 if env_label in ("bull", "bull_lean") else 3

    if change_pct >= threshold:
        gates.append({"name": "成本锚点", "passed": False,
                      "reason": f"今日涨幅{change_pct}%≥{threshold}%，追高成本过高"})
        return False, gates, f"涨幅{change_pct}%≥{threshold}%"

    gates.append({"name": "成本锚点", "passed": True,
                  "reason": f"涨幅{change_pct}%在合理范围"})

    # 门控2: 信号类型匹配环境
    sig_type = signal.get("type", "")
    if env_label in ("bear", "bear_lean") and sig_type == "breakout":
        gates.append({"name": "环境匹配", "passed": False,
                      "reason": "熊市/偏熊环境不追突破信号"})
        return False, gates, "熊市不追突破"

    gates.append({"name": "环境匹配", "passed": True,
                  "reason": f"{env['environment_cn']}接受{sig_type}信号"})

    # 门控3: 成交量确认
    vol_ratio = signal.get("vol_ratio", 1.0)
    if vol_ratio < 0.5:
        gates.append({"name": "量能确认", "passed": False,
                      "reason": f"量比{vol_ratio}<0.5，流动性不足"})
        return False, gates, "量能不足"

    gates.append({"name": "量能确认", "passed": True,
                  "reason": f"量比{vol_ratio:.1f}正常"})

    return True, gates, "门控全部通过"


# ===================== 模块3: 仓位管理 =====================

def calculate_position(signal, env, existing_count):
    """根据市场环境 + 信号强度 + 现有持仓数动态计算仓位"""
    base = env["total_position_ratio"]
    env_label = env["environment"]

    # 基础仓位金额
    if env_label == "bull":
        base_amount = 3000
    elif env_label == "bull_lean":
        base_amount = 2000
    elif env_label == "range":
        base_amount = 1500
    else:
        base_amount = 1000

    # 信号类型加成
    sig_type = signal.get("type", "")
    if sig_type == "dip_buy":
        multiplier = 1.3
    elif sig_type == "breakout":
        multiplier = 1.0
    elif sig_type == "oversold":
        multiplier = 0.7
    else:
        multiplier = 0.8

    # 分散度折扣（持仓越多，单票越小）
    diversity_discount = max(0.5, 1.0 - existing_count * 0.15)

    amount = int(base_amount * multiplier * diversity_discount)
    amount = (amount // 100) * 100  # 取整到百

    # 上限约束
    max_single = int(TOTAL_FLEXIBLE * base * SINGLE_MAX_RATIO)
    amount = min(amount, max_single, 5000)

    return max(500, amount)


# ===================== 模块4: 止盈止损 =====================

def check_exit_signals(positions_file):
    """检查持仓的止盈止损信号"""
    exit_signals = []

    if not os.path.exists(positions_file):
        return exit_signals

    with open(positions_file, "r", encoding="utf-8") as f:
        positions_data = json.load(f)

    for fund_code, pos in positions_data.get("positions", {}).items():
        if pos.get("status") != "HOLDING":
            continue

        entry_date = pos.get("entry_date", "")
        entry_nav = pos.get("entry_nav", 0)
        board = pos.get("board", "")

        # 获取板块最新K线判断
        secid = BOARDS.get(board)
        if not secid:
            continue

        klines = fetch_eastmoney_kline(secid, count=30)
        if len(klines) < 10:
            continue

        closes = [k["close"] for k in klines]
        current = closes[-1]
        ma10 = calc_ma(closes, 10)
        ma20 = calc_ma(closes, 20)
        high_10 = max(closes[-10:])

        # 计算持仓盈亏
        if entry_nav > 0:
            pnl_pct = (current - entry_nav) / entry_nav * 100
        else:
            pnl_pct = 0

        # 计算持仓天数
        try:
            entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
            days_held = (date.today() - entry_dt.date()).days
        except:
            days_held = 0

        exit_reason = None
        exit_type = None

        # 止损检查
        if pnl_pct <= STOP_LOSS_PCT * 100:
            exit_reason = f"亏损{pnl_pct:.1f}%触发-8%止损线"
            exit_type = "stop_loss"

        # 跌破MA10（趋势破坏）
        elif ma10 and current < ma10 and pnl_pct > 5:
            exit_reason = f"跌破MA10({ma10:.1f})，保护已有利润{pnl_pct:.1f}%"
            exit_type = "trend_broken"

        # 短线止盈（12%+）
        elif pnl_pct >= TAKE_PROFIT_SHORT * 100 and days_held < 20:
            exit_reason = f"短线盈利{pnl_pct:.1f}%已达止盈线"
            exit_type = "take_profit"

        # 从高点回撤超5%
        elif pnl_pct > 5 and current < high_10 * 0.95:
            exit_reason = f"从10日高点回撤超5%，保护利润"
            exit_type = "trailing_stop"

        if exit_reason:
            exit_signals.append({
                "fund_code": fund_code,
                "board": board,
                "entry_date": entry_date,
                "entry_nav": entry_nav,
                "current": round(current, 2),
                "pnl_pct": round(pnl_pct, 2),
                "days_held": days_held,
                "exit_type": exit_type,
                "reason": exit_reason,
                "action": "SELL",
            })

    return exit_signals


# ===================== 模块5: 动态优化 =====================

def update_signal_history(signals, exit_signals, env):
    """记录信号历史供复盘"""
    history_file = os.path.join(CACHE_DIR, "trading_history.json")
    history = []
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)

    today = date.today().isoformat()
    record = {
        "date": today,
        "time": datetime.now().strftime("%H:%M"),
        "environment": env["environment"],
        "environment_cn": env["environment_cn"],
        "position_ratio": env["total_position_ratio"],
        "buy_signals": len(signals),
        "exit_signals": len(exit_signals),
        "signals": [{
            "board": s["board"],
            "type": s["type"],
            "label": s["label"],
            "funds": [f["code"] for f in s.get("funds", [])],
        } for s in signals],
    }
    history.append(record)

    # 保留最近180条
    if len(history) > 180:
        history = history[-180:]

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    return history


# ===================== 主流程 =====================

def main():
    now = datetime.now()
    print(f"{'='*60}")
    print(f"五模块交易系统 — 运行时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # ===== 模块1: 市场环境判断 =====
    print("\n[模块1] 市场环境判断...")
    env = judge_market_environment()
    print(f"  综合判断: {env['environment_cn']}")
    print(f"  偏牛指数: {env['bullish_count']}/5  偏熊指数: {env['bearish_count']}/5")
    print(f"  建议总仓位: {env['total_position_ratio']*100:.0f}% (¥{env['max_position_amount']:,})")
    for name, detail in env["index_details"].items():
        if detail.get("status") not in ("data_insufficient",):
            emoji = {"bullish": "🟢", "recovering": "🟡", "bearish": "🔴", "correcting": "🟠", "neutral": "⚪"}.get(detail["status"], "⚪")
            print(f"    {emoji} {name}: {detail['current']} | MA60={detail.get('ma60','?')} MA120={detail.get('ma120','?')} | {detail['status']}")

    # ===== 模块2: 标的筛选 =====
    print(f"\n[模块2] 板块扫描与标的筛选...")
    all_signals = []
    boards_ok = 0

    for board_name, secid in BOARDS.items():
        klines = fetch_eastmoney_kline(secid, count=130)
        if len(klines) < 25:
            continue
        boards_ok += 1
        signal = detect_board_signal(klines, board_name)
        if signal:
            # 匹配基金
            funds = match_funds(signal)
            signal["funds"] = funds
            if not funds:
                # 没有预设基金的板块，尝试用相关性高的基金
                signal["funds"] = FUND_MAP.get("半导体", [("008888", "国联安中证半导体ETF联接C")])[:1]
            all_signals.append(signal)

    print(f"  成功扫描: {boards_ok}/{len(BOARDS)} 板块")
    print(f"  原始信号: {len(all_signals)} 个")

    # 门控过滤
    actionable_signals = []
    blocked_signals = []

    for sig in all_signals:
        fund_code = sig["funds"][0]["code"] if sig.get("funds") else None
        if not fund_code:
            blocked_signals.append({**sig, "block_reason": "无匹配基金"})
            continue

        allowed, gates, reason = purchase_gate(sig, fund_code, env)
        sig["gate_results"] = gates
        sig["gate_passed"] = allowed

        if allowed:
            actionable_signals.append(sig)
        else:
            blocked_signals.append({**sig, "block_reason": reason})

    # 按信号优先级排序
    priority = {"dip_buy": 0, "breakout": 1, "oversold": 2}
    actionable_signals.sort(key=lambda s: priority.get(s["type"], 9))

    print(f"  门控通过: {len(actionable_signals)} | 拦截: {len(blocked_signals)}")

    # ===== 模块3: 仓位管理 =====
    print(f"\n[模块3] 仓位管理...")
    for sig in actionable_signals:
        sig["position"] = calculate_position(sig, env, len(actionable_signals))
        print(f"  {sig['label']} {sig['board']} → ¥{sig['position']:,} | {sig['funds'][0]['code']} {sig['funds'][0]['name']}")

    total_suggested = sum(s["position"] for s in actionable_signals[:5])

    # ===== 模块4: 止盈止损 =====
    print(f"\n[模块4] 止盈止损检查...")
    positions_file = os.path.join(SCRIPT_DIR, "positions.json")
    exit_signals = check_exit_signals(positions_file)
    if exit_signals:
        for es in exit_signals:
            emoji = {"stop_loss": "🔴", "take_profit": "🟢", "trend_broken": "🟡", "trailing_stop": "🟠"}.get(es["exit_type"], "⚪")
            print(f"  {emoji} {es['fund_code']} {es['board']} | 盈亏{es['pnl_pct']:+.1f}% | 持有{es['days_held']}天 | {es['reason']}")
    else:
        print("  无退出信号")

    # ===== 模块5: 动态优化 =====
    print(f"\n[模块5] 记录历史...")
    history = update_signal_history(actionable_signals, exit_signals, env)
    print(f"  累计记录: {len(history)} 个交易日")

    # ===== 构建输出 =====
    output = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "run_time": now.strftime("%H:%M"),
        "total_assets": TOTAL_ASSETS,
        "total_flexible": TOTAL_FLEXIBLE,
        "module_1_environment": {
            "env": env["environment"],
            "env_cn": env["environment_cn"],
            "position_ratio": env["total_position_ratio"],
            "max_position": env["max_position_amount"],
            "bullish_count": env["bullish_count"],
            "bearish_count": env["bearish_count"],
            "index_details": env["index_details"],
        },
        "module_2_selection": {
            "scanned": boards_ok,
            "total": len(BOARDS),
            "raw_signals": len(all_signals),
            "actionable_signals": len(actionable_signals),
            "blocked_signals": len(blocked_signals),
            "signals": [{k: v for k, v in s.items() if k != "gate_results"} for s in actionable_signals],
            "blocked": [{k: v for k, v in s.items() if k != "gate_results"} for s in blocked_signals[:10]],
        },
        "module_3_position": {
            "total_suggested": total_suggested,
            "single_max": int(TOTAL_FLEXIBLE * env["total_position_ratio"] * SINGLE_MAX_RATIO),
            "strategy": env["environment_cn"],
            "diversification_note": f"建议分散到{min(len(actionable_signals), 5)}只基金",
        },
        "module_4_exit": {
            "exit_signals": exit_signals,
            "rules": {
                "stop_loss": f"{STOP_LOSS_PCT*100:.0f}% 硬止损",
                "take_profit_short": f"{TAKE_PROFIT_SHORT*100:.0f}% 短线止盈",
                "take_profit_trend": f"{TAKE_PROFIT_TREND*100:.0f}% 趋势止盈",
                "trailing_stop": "从高点回撤>5% 移动止盈",
            },
        },
        "module_5_optimization": {
            "history_days": len(history),
            "recent_environments": [h["environment"] for h in history[-10:]],
        },
        "summary": {
            "environment": env["environment_cn"],
            "buy_signals": len(actionable_signals),
            "exit_signals": len(exit_signals),
            "today_budget": min(total_suggested, env["max_position_amount"]),
            "action_required": len(actionable_signals) > 0 or len(exit_signals) > 0,
            "key_action": "",
        },
    }

    # 生成关键行动建议
    if env["environment"] in ("bear", "bear_lean") and not actionable_signals:
        output["summary"]["key_action"] = "市场偏熊，持有现金观望"
    elif actionable_signals:
        top = actionable_signals[0]
        output["summary"]["key_action"] = f"优先关注 {top['board']} ({top['label']})"
    if exit_signals:
        output["summary"]["key_action"] += " | 有持仓需退出"

    # 保存JSON
    json_path = os.path.join(OUTPUT_DIR, "trading_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n数据已保存: {json_path}")

    # ==================== 生成HTML Dashboard ====================
    html_content = generate_dashboard_html(output, env)
    html_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Dashboard已保存: {html_path}")

    # 同时复制到根目录（GitHub Pages 可以从根目录或 /output 读取）
    root_html = os.path.join(SCRIPT_DIR, "index.html")
    with open(root_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 打印最终摘要
    print(f"\n{'='*60}")
    print(f"运行完成 | {output['summary']['key_action']}")
    print(f"{'='*60}")

    return output



def generate_dashboard_html(data, env):
    """生成教练式 Dashboard - 每日操盘指南"""
    import json as _json
    now = datetime.now()
    m1 = data["module_1_environment"]
    m2 = data["module_2_selection"]
    m3 = data["module_3_position"]
    m4 = data["module_4_exit"]

    # 读取心法训练数据
    mindset = {}
    mindset_file = os.path.join(CACHE_DIR, "mindset_training.json")
    if os.path.exists(mindset_file):
        with open(mindset_file, "r", encoding="utf-8") as f:
            mindset = _json.load(f)

    # 读取豆包Prompt
    prompt_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doubao_prompt.txt")
    doubao_prompt = ""
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            doubao_prompt = f.read()
    else:
        doubao_prompt = "（Prompt文件缺失，请联系管理员）"

    # 环境颜色
    env_colors = {
        "bull": ("#22c55e", "#22c55e"),
        "bull_lean": ("#84cc16", "#84cc16"),
        "range": ("#f59e0b", "#f59e0b"),
        "bear_lean": ("#f97316", "#f97316"),
        "bear": ("#ef4444", "#ef4444"),
    }
    ec = env_colors.get(m1["env"], ("#9ca3af", "#9ca3af"))

    # ---- 三阶段进度计算 ----
    def calc_phase_progress(stage_num):
        records = mindset.get("records", [])
        if not records:
            return 0
        if stage_num == 1:
            total = len(records)
            disciplined = sum(1 for r in records if r.get("disciplined", False))
            return round(disciplined / total * 100) if total > 0 else 0
        elif stage_num == 2:
            modes = mindset.get("mode_exploration", {}).get("tried_modes", [])
            current = mindset.get("mode_exploration", {}).get("current_mode", "")
            win_rate = mindset.get("mode_exploration", {}).get("monthly_win_rate", 0)
            if current:
                return min(100, win_rate * 2)
            return min(100, len(modes) * 20) if modes else 0
        elif stage_num == 3:
            total = len(records)
            invalid = sum(1 for r in records if r.get("is_impulsive", False) or r.get("impulsive_count", 0) > 0)
            ratio = round(invalid / total * 100) if total > 0 else 0
            return max(0, 100 - ratio)
        return 0

    p1 = calc_phase_progress(1)
    p2 = calc_phase_progress(2)
    p3 = calc_phase_progress(3)

    def progress_bar(pct, label, color="#f59e0b"):
        filled = max(1, round(pct / 10))
        empty = max(0, 10 - filled)
        bar = '<span style="color:' + color + '">' + ("■" * filled) + '</span>' + ("□" * empty)
        return '<div class="progress-row"><span class="phase-label">' + label + '</span><span class="phase-bar">' + bar + '</span><span class="phase-pct">' + str(pct) + '%</span></div>'

    # ---- 今日待办时间逻辑 ----
    hour = now.hour
    if hour < 11:
        todo_step2 = "11:00 系统自动扫描信号，刷新页面查看买卖建议"
    elif hour < 14:
        todo_step2 = "14:30 系统再次扫描，刷新页面查看"
    else:
        todo_step2 = "今日扫描已完成。打开同花顺+养基宝+支付宝，截图做复盘"

    # ---- 信号表格 ----
    signals_html = ""
    if m2["actionable_signals"] > 0:
        for sig in m2["signals"]:
            fund_info = ""
            if sig.get("funds"):
                f = sig["funds"][0]
                fund_info = f["code"] + " " + f["name"]
            pos = sig.get("position", 0)
            sc = {
                "dip_buy": "#3b82f6",
                "breakout": "#22c55e",
                "oversold": "#f59e0b"
            }.get(sig.get("type", ""), "#9ca3af")
            signals_html += "<tr><td><span style='color:" + sc + ";font-weight:600'>" + sig.get("label", "") + "</span></td><td>" + sig["board"] + "</td><td>" + format(sig.get("change_pct", 0), "+.1f") + "%</td><td style='color:#f59e0b'>\u00a5" + format(pos, ",") + "</td><td style='font-size:0.8rem;color:#9ca3af'>" + fund_info + "</td></tr>"
    else:
        signals_html = "<tr><td colspan='5' style='text-align:center;color:#6b7280;padding:2rem'>今日无买入信号 — 不做也是操作</td></tr>"

    exit_html = ""
    if m4["exit_signals"]:
        for es in m4["exit_signals"]:
            ex_c = {
                "stop_loss": "#ef4444",
                "take_profit": "#22c55e",
                "trend_broken": "#f59e0b",
                "trailing_stop": "#f97316"
            }.get(es.get("exit_type", ""), "#9ca3af")
            exit_html += "<div class='exit-row' style='border-left:3px solid " + ex_c + "'><strong>" + es["fund_code"] + "</strong> " + es.get("board", "") + "<span style='float:right;color:" + ex_c + "'>" + format(es.get("pnl_pct", 0), "+.1f") + "%</span><div style='font-size:0.8rem;color:#9ca3af'>" + es["reason"] + " | " + str(es.get("days_held", 0)) + "天</div></div>"
    else:
        exit_html = "<div style='color:#6b7280;text-align:center;padding:1rem'>无退出信号</div>"

    # ---- 修炼日志表 ----
    log_rows = ""
    for r in reversed(mindset.get("records", [])[-10:]):
        d_icon = "OK" if r.get("disciplined") else "!!"
        imp = r.get("impulsive_count", 0)
        log_rows += "<tr><td>" + str(r.get("date", "")) + "</td><td>" + d_icon + "</td><td>" + str(imp) + "</td><td>" + str(r.get("mindset_note", "")) + "</td><td>" + str(r.get("market_env", "")) + "</td></tr>"

    # ---- 指数卡片 ----
    idx_cards = ""
    for name, detail in m1["index_details"].items():
        if detail.get("status") == "data_insufficient":
            continue
        s = detail["status"]
        sc = {
            "bullish": "#22c55e", "recovering": "#f59e0b",
            "bearish": "#ef4444", "correcting": "#f97316",
            "neutral": "#9ca3af"
        }.get(s, "#9ca3af")
        sl = {
            "bullish": "多头", "recovering": "恢复",
            "bearish": "空头", "correcting": "调整",
            "neutral": "中性"
        }.get(s, s)
        idx_cards += "<div class='idx-card' style='border-left:3px solid " + sc + "'><div class='idx-name'>" + name + "</div><div class='idx-price'>" + str(detail["current"]) + "</div><span class='tag' style='background:" + sc + "20;color:" + sc + "'>" + sl + "</span></div>"

    # 豆包Prompt HTML转义（防止注入HTML）
    prompt_safe = doubao_prompt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # ---- 完整HTML ----
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>操盘手每日修炼 · 交易系统</title>
<style>
  :root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#c9d1d9; --dim:#8b949e; --gold:#f59e0b; --green:#22c55e; --red:#ef4444; --blue:#3b82f6; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; line-height:1.6; padding:1rem; }
  .container { max-width:860px; margin:0 auto; }

  .coach-banner {
    background: linear-gradient(135deg, rgba(245,158,11,0.12), rgba(245,158,11,0.04));
    border:1px solid rgba(245,158,11,0.25); border-radius:14px;
    padding:1.25rem; text-align:center; margin-bottom:1rem;
  }
  .coach-banner .greeting { font-size:0.85rem; color:var(--dim); }
  .coach-banner .mission { font-size:1.4rem; font-weight:800; color:var(--gold); margin:0.3rem 0; }
  .coach-banner .env-line { font-size:0.85rem; color:var(--dim); }

  .todo-panel {
    background:var(--card); border:1px solid var(--border); border-radius:12px;
    padding:1.25rem; margin-bottom:1rem;
  }
  .todo-panel h3 { font-size:1rem; color:#f0f6fc; margin-bottom:0.75rem; }
  .todo-item {
    display:flex; align-items:flex-start; gap:0.65rem; padding:0.5rem 0;
    border-bottom:1px solid rgba(255,255,255,0.03);
  }
  .todo-num { width:28px;height:28px;border-radius:50%;background:rgba(59,130,246,0.15);color:var(--blue);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.8rem;flex-shrink:0; }
  .todo-text { font-size:0.9rem; color:var(--text); }
  .todo-hint { font-size:0.75rem; color:var(--dim); margin-top:0.15rem; }

  .prompt-box {
    background:var(--card); border:1px solid var(--border); border-radius:12px;
    padding:1.25rem; margin-bottom:1rem; position:relative;
  }
  .prompt-box h3 { font-size:1rem; color:var(--blue); margin-bottom:0.5rem; }
  .prompt-content {
    background:#0d1117; border:1px solid var(--border); border-radius:8px;
    padding:1rem; font-size:0.78rem; color:var(--dim); white-space:pre-wrap;
    max-height:300px; overflow-y:auto; margin-bottom:0.75rem;
    font-family:"SF Mono","Fira Code",monospace; line-height:1.5;
  }
  .btn-copy {
    display:inline-flex; align-items:center; gap:0.35rem; padding:0.5rem 1rem;
    background:rgba(59,130,246,0.12); border:1px solid rgba(59,130,246,0.3);
    border-radius:8px; color:var(--blue); font-size:0.85rem; cursor:pointer;
    font-weight:600; transition:all 0.2s;
  }
  .btn-copy:hover { background:rgba(59,130,246,0.2); }
  .btn-copy.copied { background:rgba(34,197,94,0.12); border-color:rgba(34,197,94,0.3); color:var(--green); }
  .paste-area {
    margin-top:0.75rem; display:none;
  }
  .paste-area.show { display:block; }
  .paste-area textarea {
    width:100%; background:#0d1117; border:1px dashed var(--gold); border-radius:8px;
    padding:0.75rem; color:var(--gold); font-size:0.8rem; font-family:monospace;
    resize:vertical; min-height:80px;
  }
  .btn-paste { margin-top:0.5rem; padding:0.4rem 0.9rem; background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.3); border-radius:8px; color:var(--gold); font-size:0.8rem; cursor:pointer; }
  .btn-paste:hover { background:rgba(245,158,11,0.2); }

  .mindset-panel {
    background:var(--card); border:1px solid var(--border); border-radius:12px;
    padding:1.25rem; margin-bottom:1rem;
  }
  .mindset-panel h3 { font-size:1rem; color:#f0f6fc; margin-bottom:0.75rem; }
  .progress-row {
    display:flex; align-items:center; gap:0.6rem; padding:0.35rem 0;
  }
  .phase-label { width:110px; font-size:0.82rem; color:var(--dim); flex-shrink:0; }
  .phase-bar { font-size:0.85rem; letter-spacing:2px; }
  .phase-pct { font-size:0.82rem; color:var(--gold); font-weight:700; width:40px;text-align:right; }

  .log-table { width:100%; border-collapse:collapse; font-size:0.78rem; margin-top:0.5rem; }
  .log-table th { background:rgba(255,255,255,0.02); padding:0.4rem 0.5rem; text-align:left; font-weight:600; color:var(--dim); border-bottom:1px solid var(--border); }
  .log-table td { padding:0.35rem 0.5rem; border-bottom:1px solid rgba(255,255,255,0.02); }
  .log-empty { text-align:center; color:var(--dim); padding:1rem; font-size:0.8rem; }

  details { margin-bottom:1rem; }
  details summary {
    background:var(--card); border:1px solid var(--border); border-radius:10px;
    padding:0.8rem 1.25rem; cursor:pointer; font-weight:600; color:var(--dim);
    font-size:0.9rem; user-select:none;
  }
  details summary:hover { color:var(--text); }
  .detail-card { background:var(--card); border:1px solid var(--border); border-top:none; border-radius:0 0 10px 10px; padding:1.25rem; }

  .idx-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:0.5rem; margin-bottom:1rem; }
  .idx-card { background:rgba(255,255,255,0.02); border-radius:8px; padding:0.55rem; }
  .idx-name { font-size:0.75rem; color:var(--dim); }
  .idx-price { font-size:1rem; font-weight:700; color:#f0f6fc; }

  .stat-row { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:0.75rem; }
  .stat { text-align:center; padding:0.5rem 0.75rem; }
  .stat .num { font-size:1.2rem; font-weight:800; color:#f0f6fc; }
  .stat .lbl { font-size:0.7rem; color:var(--dim); }

  table { width:100%; border-collapse:collapse; font-size:0.8rem; }
  th { background:rgba(255,255,255,0.02); padding:0.45rem 0.6rem; text-align:left; font-weight:600; color:var(--dim); border-bottom:1px solid var(--border); }
  td { padding:0.4rem 0.6rem; border-bottom:1px solid rgba(255,255,255,0.02); }

  .exit-row { padding:0.5rem 0.7rem; margin-bottom:0.3rem; background:rgba(255,255,255,0.02); border-radius:6px; font-size:0.85rem; }

  .tag { display:inline-block; padding:0.1rem 0.4rem; border-radius:10px; font-size:0.65rem; font-weight:600; }

  .footer { text-align:center; padding:1.5rem 0; color:var(--dim); font-size:0.7rem; border-top:1px solid var(--border); margin-top:1.5rem; }
</style>
</head>
<body>
<div class="container">

<div class="coach-banner">
  <div class="greeting">操盘手每日修炼</div>
  <div class="mission">练心，而非练术</div>
  <div class="env-line">
    今日市场：<span style="color:""" + ec[0] + """;font-weight:700">""" + m1["env_cn"] + """</span>
    &nbsp;|&nbsp; 仓位建议：""" + str(int(m1["position_ratio"] * 100)) + """%
    &nbsp;|&nbsp; 更新：""" + now.strftime("%m-%d %H:%M") + """
  </div>
</div>

<div class="todo-panel">
  <h3>今日待办【同花顺 + 养基宝 + 支付宝】</h3>
  <div class="todo-item">
    <div class="todo-num">1</div>
    <div>
      <div class="todo-text">截图三张：<strong>同花顺大盘</strong> + <strong>养基宝持仓</strong> + <strong>支付宝交易记录</strong></div>
    </div>
  </div>
  <div class="todo-item">
    <div class="todo-num">2</div>
    <div>
      <div class="todo-text">打开豆包，粘贴下方Prompt，同时上传三张截图，获取JSON分析结果</div>
    </div>
  </div>
  <div class="todo-item">
    <div class="todo-num">3</div>
    <div>
      <div class="todo-text">复制豆包返回的JSON，点击下方「粘贴分析结果」按钮贴进去</div>
      <div class="todo-hint">数据存到浏览器localStorage，合并修炼记录，刷新页面即可看到进度变化</div>
    </div>
  </div>
  <div class="todo-item">
    <div class="todo-num">4</div>
    <div>
      <div class="todo-text">""" + todo_step2 + """</div>
      <div class="todo-hint">每天坚持三步，两年轻舟已过万重山</div>
    </div>
  </div>
</div>

<div class="prompt-box">
  <h3>豆包Prompt · 一键复制（同花顺+养基宝+支付宝三图版）</h3>
  <div class="prompt-content" id="promptText">""" + prompt_safe + """</div>
  <button class="btn-copy" id="btnCopy" onclick="copyPrompt()">
    <span id="copyIcon">📋</span> <span id="copyLabel">复制Prompt</span>
  </button>
  <div style="margin-top:0.75rem;font-size:0.78rem;color:var(--dim)">
    复制后粘贴到豆包对话框，同时上传 <strong>同花顺 + 养基宝 + 支付宝</strong> 三张截图
  </div>

  <div style="margin-top:1rem">
    <button class="btn-paste" onclick="document.getElementById('pasteBox').classList.toggle('show')">
      粘贴分析结果
    </button>
    <div class="paste-area" id="pasteBox">
      <textarea id="jsonInput" placeholder="把豆包返回的JSON粘贴到这里..."></textarea>
      <button class="btn-paste" onclick="mergeResult()" style="margin-top:0.4rem">合并到修炼记录</button>
      <div id="mergeMsg" style="font-size:0.75rem;color:var(--green);margin-top:0.3rem"></div>
    </div>
  </div>
</div>

<div class="mindset-panel">
  <h3>修炼进度 · 三阶段</h3>
  """ + progress_bar(p1, "一阶·练执行力", "#3b82f6") + """
  """ + progress_bar(p2, "二阶·找交易模式", "#84cc16") + """
  """ + progress_bar(p3, "三阶·去无效交易", "#22c55e") + """
  <div style="font-size:0.72rem;color:var(--dim);margin-top:0.5rem">
    目标：第一阶段→买卖不抖 | 第二阶段→月成功率>=50% | 第三阶段→感觉交易很无聊
  </div>

  <div style="margin-top:0.75rem">
    <strong style="font-size:0.82rem;color:var(--dim)">近期修炼记录</strong>
    """ + ("<table class='log-table'><tr><th>日期</th><th>守纪律</th><th>冲动</th><th>心态</th><th>市场</th></tr>" + log_rows + "</table>" if log_rows else "<div class='log-empty'>等待首次截图分析 — 按上方待办步骤开始</div>") + """
  </div>
</div>

<details>
  <summary>完整交易数据（五模块 · 点击展开）</summary>
  <div class="detail-card">
    <div class="idx-grid">""" + idx_cards + """</div>
    <div class="stat-row">
      <div class="stat"><div class="num">""" + str(m2["scanned"]) + """</div><div class="lbl">板块扫描</div></div>
      <div class="stat"><div class="num">""" + str(m2["actionable_signals"]) + """</div><div class="lbl">买入信号</div></div>
      <div class="stat"><div class="num">""" + str(m2["blocked_signals"]) + """</div><div class="lbl">门控拦截</div></div>
      <div class="stat"><div class="num">¥""" + format(m3["total_suggested"], ",") + """</div><div class="lbl">建议仓位</div></div>
    </div>
    <table><tr><th>信号</th><th>板块</th><th>涨跌</th><th>仓位</th><th>匹配基金</th></tr>""" + signals_html + """</table>
    <div style="margin-top:1rem">
      <strong style="color:var(--dim);font-size:0.85rem">退出信号</strong>
      """ + exit_html + """
    </div>
    <div style="margin-top:0.75rem;font-size:0.78rem;color:var(--dim)">
      止损-8% | 短线止盈+12% | 趋势止盈+18% | 移动止盈高点回撤&gt;5% |
      历史记录 """ + str(data["module_5_optimization"]["history_days"]) + """ 天
    </div>
  </div>
</details>

<div class="footer">
  交易系统 + 无忌心法 &nbsp;|&nbsp; 先练心，再练术 &nbsp;|&nbsp; 自动运行 11:00 / 14:30
</div>

</div>

<script>
function copyPrompt() {
  var text = document.getElementById('promptText').innerText;
  navigator.clipboard.writeText(text).then(function() {
    var btn = document.getElementById('btnCopy');
    btn.classList.add('copied');
    document.getElementById('copyIcon').innerText = 'OK';
    document.getElementById('copyLabel').innerText = '已复制！去豆包粘贴吧';
    setTimeout(function() {
      btn.classList.remove('copied');
      document.getElementById('copyIcon').innerText = '📋';
      document.getElementById('copyLabel').innerText = '复制Prompt';
    }, 3000);
  });
}

function mergeResult() {
  var raw = document.getElementById('jsonInput').value.trim();
  var msg = document.getElementById('mergeMsg');
  if (!raw) { msg.innerText = '请先粘贴豆包返回的JSON'; msg.style.color='var(--red)'; return; }
  try {
    var obj = JSON.parse(raw);
    var stored = localStorage.getItem('mindset_records');
    var records = stored ? JSON.parse(stored) : [];
    records = records.filter(function(r) { return r.date !== obj.date; });
    records.push(obj);
    records.sort(function(a,b) { return a.date.localeCompare(b.date); });
    localStorage.setItem('mindset_records', JSON.stringify(records));
    msg.innerText = '已合并！共 ' + records.length + ' 条记录。刷新页面查看更新后的进度。';
    msg.style.color = 'var(--green)';
    document.getElementById('jsonInput').value = '';
  } catch(e) {
    msg.innerText = 'JSON格式有误：' + e.message;
    msg.style.color = 'var(--red)';
  }
}

(function() {
  var stored = localStorage.getItem('mindset_records');
  if (stored) {
    var records = JSON.parse(stored);
    if (records.length > 0) {
      console.log('已加载 ' + records.length + ' 条修炼记录');
    }
  }
})();
</script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    main()
