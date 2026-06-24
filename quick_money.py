#!/usr/bin/env python3
"""
快钱模块 - 全市场高波动板块扫描 + C类基金自动匹配
数据源: 东方财富免费API
缓存策略: 增量更新K线，每天只拉取新交易日数据

用法:
  python3 quick_money.py           # 更新 quick_money.json
  python3 quick_money.py --dry-run # 只打印信号
"""
import json
import os
import sys
import urllib.request
import urllib.parse
import time
from datetime import datetime, date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(SCRIPT_DIR, "cache", "board_kline_cache.json")
OUTPUT_FILE = os.path.join(os.path.dirname(SCRIPT_DIR), "output", "quick_money.json")
SIGNAL_HISTORY_FILE = os.path.join(SCRIPT_DIR, "cache", "signal_history.json")
FUND_ESTIMATE_CACHE = os.path.join(SCRIPT_DIR, "cache", "fund_estimate_cache.json")

# ========== 配置 ==========
TOTAL_FLEXIBLE = 96000  # 灵活资金总额
TOTAL_MONEY_FUND = 50000  # 货币基金约5万
TOTAL_ASSETS = TOTAL_FLEXIBLE + TOTAL_MONEY_FUND  # 总资产约14.6万
MAX_TOTAL_POSITION = 20000  # 快钱总仓位上限
MIN_FUND_SCALE = 0.5  # 基金最小规模(亿)，防清盘风险
POSITIONS_FILE = os.path.join(SCRIPT_DIR, "positions.json")  # 持仓状态文件

# 25个高波动概念板块（东财代码 BKxxxx）
BOARDS = {
    # 半导体链
    "科创芯片": "90.BK0990",
    "存储芯片": "90.BK1135", 
    "半导体": "90.BK1036",
    "先进封装": "90.BK1032",
    "汽车芯片": "90.BK0962",
    # AI算力链
    "CPO": "90.BK1099",
    "光通信": "90.BK1098",
    "算力": "90.BK1134",
    "液冷服务器": "90.BK1156",
    "铜缆高速连接": "90.BK1168",
    # 消费电子
    "PCB": "90.BK0877",
    "AI手机": "90.BK1162",
    "智能穿戴": "90.BK0862",
    "消费电子": "90.BK0878",
    "AI眼镜": "90.BK1170",
    # 新能源/新质生产力
    "固态电池": "90.BK0968",
    "低空经济": "90.BK1166",
    "人形机器人": "90.BK1158",
    "商业航天": "90.BK1161",
    # 周期/题材
    "创新药": "90.BK0939",
    "稀土永磁": "90.BK0579",
    "数据要素": "90.BK1142",
    "量子科技": "90.BK1076",
    "脑机接口": "90.BK1124",
    "数字货币": "90.BK0903",
}

# 用户已持仓基金（用于避免重复推荐）
EXISTING_HOLDINGS = {"005844", "006503", "025209"}


# ========== 持仓状态管理 ==========
def load_positions():
    """加载当前持仓状态"""
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"positions": {}, "total_invested": 0, "history": []}


def save_positions(positions_data):
    """保存持仓状态"""
    pos_dir = os.path.dirname(POSITIONS_FILE)
    if pos_dir:
        os.makedirs(pos_dir, exist_ok=True)
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(positions_data, f, ensure_ascii=False, indent=2)


def get_days_held(entry_date_str):
    """计算持仓天数"""
    try:
        entry = datetime.strptime(entry_date_str, "%Y-%m-%d")
        return (date.today() - entry.date()).days
    except:
        return 0


def purchase_gate(signal, fund_code, positions_data, fund_estimate=None):
    """
    申购门控 - 四道硬约束，全部通过才放行。
    返回: (allowed: bool, gate_results: list, reason: str)
    """
    gates = []
    
    # ===== 门控1: 费率窗口检查 =====
    # 检查同基金是否7天内买过（不能再买，否则锁死流动性）
    pos = positions_data["positions"].get(fund_code, {})
    if pos:
        days_held = get_days_held(pos["entry_date"])
        if days_held < 7:
            gates.append({
                "gate": 1,
                "name": "费率窗口",
                "passed": False,
                "reason": f"同基金持仓仅{days_held}天，7天内追加会锁死所有资金(1.5%罚息)，禁止追加",
                "severity": "BLOCK"
            })
            return False, gates, f"门控1未通过: 同基金{fund_code}持仓{days_held}天<7天"
        elif days_held < 30:
            gates.append({
                "gate": 1,
                "name": "费率窗口",
                "passed": True,
                "reason": f"同基金持仓{days_held}天，仍在0.5%费区内，追加需谨慎",
                "severity": "WARN"
            })
        else:
            gates.append({
                "gate": 1,
                "name": "费率窗口",
                "passed": True,
                "reason": f"同基金持仓{days_held}天，0费率区，无限制",
                "severity": "OK"
            })
    else:
        gates.append({
            "gate": 1,
            "name": "费率窗口",
            "passed": True,
            "reason": "新开仓，7天内不可赎回(1.5%)，需有把握",
            "severity": "OK"
        })
    
    # ===== 门控2: 成本锚点检查 =====
    change_pct = signal.get("change_pct", 0)
    if change_pct >= 5:
        gates.append({
            "gate": 2,
            "name": "成本锚点",
            "passed": False,
            "reason": f"今日涨幅{change_pct}%>=5%，追高成本锚点过高，等阴线再入",
            "severity": "BLOCK"
        })
        return False, gates, f"门控2未通过: 今日涨幅{change_pct}%>=5%"
    elif change_pct >= 3:
        gates.append({
            "gate": 2,
            "name": "成本锚点",
            "passed": False,
            "reason": f"今日涨幅{change_pct}%>=3%，追高不建议。如需买入等回调至MA10附近",
            "severity": "BLOCK"
        })
        return False, gates, f"门控2未通过: 今日涨幅{change_pct}%>=3%"
    else:
        gates.append({
            "gate": 2,
            "name": "成本锚点",
            "passed": True,
            "reason": f"今日涨幅{change_pct}%，成本锚点合理",
            "severity": "OK"
        })
    
    # ===== 门控3: 信号一致性检查 =====
    if fund_estimate:
        est_direction = "up" if fund_estimate["change_pct"] > 0 else "down"
        board_direction = "up" if change_pct > 0 else "down"
        if est_direction != board_direction:
            gates.append({
                "gate": 3,
                "name": "信号一致性",
                "passed": False,
                "reason": f"板块{change_pct:+.2f}%与基金估算{fund_estimate['change_pct']:+.2f}%方向矛盾，估值不可靠",
                "severity": "BLOCK"
            })
            return False, gates, "门控3未通过: 板块与基金方向矛盾"
    
    # 检查板块涨幅绝对值 vs 基金估值涨幅绝对值 偏差
    if fund_estimate and abs(fund_estimate["change_pct"] - change_pct) > 5:
        gates.append({
            "gate": 3,
            "name": "信号一致性",
            "passed": False,
            "reason": f"板块{change_pct:+.2f}%与基金估算{fund_estimate['change_pct']:+.2f}%偏差>5%，估值异常",
            "severity": "BLOCK"
        })
        return False, gates, "门控3未通过: 板块与基金偏差过大"
    
    gates.append({
        "gate": 3,
        "name": "信号一致性",
        "passed": True,
        "reason": "板块与基金信号一致",
        "severity": "OK"
    })
    
    # ===== 门控4: 仓位上限检查 =====
    total_invested = positions_data.get("total_invested", 0)
    signal_position = signal.get("position", 500)
    new_total = total_invested + signal_position
    
    if new_total > MAX_TOTAL_POSITION:
        remaining = MAX_TOTAL_POSITION - total_invested
        gates.append({
            "gate": 4,
            "name": "仓位上限",
            "passed": False,
            "reason": f"已投{total_invested}+本次{signal_position}={new_total}超过上限{MAX_TOTAL_POSITION}，剩余额度{remaining}",
            "severity": "BLOCK"
        })
        # 不算完全阻止，降额度
        if remaining >= 200:
            signal["position"] = remaining
            gates[-1]["reason"] += f"，建议降为{remaining}元"
            # 不return False，允许降额通过
    
    gates.append({
        "gate": 4,
        "name": "仓位上限",
        "passed": True,
        "reason": f"已投{total_invested}+{signal_position}={new_total}≤{MAX_TOTAL_POSITION}",
        "severity": "OK"
    })
    
    return True, gates, "全部门控通过"


# ========== 退出/止盈信号检测 ==========
def detect_exit_signals(klines, fund_code, positions_data):
    """
    检测已有持仓的退出信号
    返回: exit_signal 或 None
    """
    pos = positions_data["positions"].get(fund_code)
    if not pos:
        return None
    
    days_held = get_days_held(pos["entry_date"])
    closes = [k["close"] for k in klines]
    latest = klines[-1]
    entry_price = pos.get("entry_nav", 0)
    
    if entry_price <= 0:
        return None
    
    pnl_pct = (latest["close"] - entry_price) / entry_price * 100
    
    exit_signal = None
    
    # 止损: 持仓>7天 + 相对成本跌>8% → 强制止损
    if days_held > 7 and pnl_pct <= -8:
        exit_signal = {
            "type": "stop_loss",
            "label": "🛑 强制止损",
            "reason": f"持仓{days_held}天亏损{pnl_pct:.1f}%超8%止损线",
            "action": "赎回全部"
        }
    
    # 止盈: 涨幅>15% + 出现高换手/长上影 → 减半仓
    elif pnl_pct >= 15:
        # 检查是否高换手（量比>2）或长上影（上影线>实体2倍）
        vol_ratio = latest["volume"] / (sum([k["volume"] for k in klines[-6:-1]]) / 5) if len(klines) >= 6 else 1
        upper_shadow = latest["high"] - max(latest["open"], latest["close"])
        body = abs(latest["close"] - latest["open"])
        long_shadow = (body > 0 and upper_shadow / body > 2)
        
        if vol_ratio >= 2 or long_shadow:
            exit_signal = {
                "type": "take_profit",
                "label": "💰 止盈信号",
                "reason": f"持仓{days_held}天盈利{pnl_pct:.1f}%{'，放量' if vol_ratio>=2 else '，长上影'}",
                "action": "减仓50%"
            }
    
    # 连跌破MA20: 持仓>7天 + 连跌3天 + 跌破MA20 → 减仓
    elif days_held > 7:
        ma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        if ma20 and latest["close"] < ma20 and is_consecutive_drop(klines, 3):
            exit_signal = {
                "type": "trend_break",
                "label": "📉 趋势破位",
                "reason": f"连跌3天+跌破MA20({ma20:.1f})，持仓{days_held}天",
                "action": "减仓50%或清仓"
            }
    
    return exit_signal


# ========== P3: 基金实时估值 API ==========
def fetch_fund_estimate(fund_code):
    """获取基金实时估算净值（天天基金API）"""
    if not fund_code or len(fund_code) < 6:
        return None
    
    url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js?rt={int(time.time()*1000)}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://fund.eastmoney.com/"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode()
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            return {
                "code": fund_code,
                "name": data.get("name", ""),
                "nav_estimate": float(data.get("gsz", 0)),
                "change_pct": float(data.get("gszzl", 0)),
                "yesterday_nav": float(data.get("dwjz", 0)),
                "update_time": data.get("gztime", ""),
            }
        except:
            if attempt < 2:
                time.sleep(1)
    return None


def batch_fetch_estimates(fund_codes):
    """批量获取基金估值，带缓存"""
    cache = {}
    cache_dir = os.path.dirname(FUND_ESTIMATE_CACHE)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
    
    if os.path.exists(FUND_ESTIMATE_CACHE):
        try:
            with open(FUND_ESTIMATE_CACHE, "r") as f:
                cached = json.load(f)
            cache_time = cached.get("_timestamp", "")
            today_str = date.today().strftime("%Y-%m-%d")
            if cache_time.startswith(today_str) and datetime.now().hour < 15:
                cache = cached
        except:
            pass
    
    results = {}
    for code in fund_codes:
        if code in cache and code != "_timestamp":
            results[code] = cache[code]
        else:
            est = fetch_fund_estimate(code)
            if est:
                results[code] = est
                cache[code] = est
            time.sleep(0.2)
    
    cache["_timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(FUND_ESTIMATE_CACHE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    
    return results


# ========== P3: 信号有效期管理 ==========
def load_signal_history():
    """加载信号历史"""
    if os.path.exists(SIGNAL_HISTORY_FILE):
        with open(SIGNAL_HISTORY_FILE, "r") as f:
            return json.load(f)
    return {}


def save_signal_history(history):
    hist_dir = os.path.dirname(SIGNAL_HISTORY_FILE)
    if hist_dir:
        os.makedirs(hist_dir, exist_ok=True)
    with open(SIGNAL_HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def check_signal_freshness(signal, history):
    """
    检查信号新鲜度：
    - 新信号 → fresh (第一天出现)
    - 连续出现 → persistent (持续2-3天，还可执行)
    - 过期 → stale (超过3天)
    - 失效 → invalidated (今天方向反转)
    """
    board = signal["board"]
    sig_type = signal["type"]
    key = f"{board}_{sig_type}"
    
    today_str = date.today().strftime("%Y-%m-%d")
    today_change = signal.get("change_pct", 0)
    
    if key not in history:
        # 全新信号
        history[key] = {
            "first_seen": today_str,
            "last_seen": today_str,
            "seen_count": 1,
            "direction_at_first": "up" if today_change > 0 else "down",
        }
        return "fresh"
    
    entry = history[key]
    first_date = datetime.strptime(entry["first_seen"], "%Y-%m-%d").date()
    days_since_first = (date.today() - first_date).days
    
    # 反转检测：比较今天方向与首次出现方向
    first_direction = entry["direction_at_first"]
    today_direction = "up" if today_change > 0 else "down"
    
    if days_since_first >= 0 and first_direction != today_direction:
        # 放量突破信号：方向反转 → 失效
        if sig_type == "breakout" and today_direction == "down":
            return "invalidated"
        # 缩量止跌信号：如果放量反弹，止跌确认
        if sig_type == "dip_buy" and today_direction == "up" and signal.get("vol_ratio", 0) > 1.5:
            entry["last_seen"] = today_str
            entry["seen_count"] = entry.get("seen_count", 0) + 1
            return "confirmed"
        # 反转但非标准失效模式，仅标记
        entry["direction_reversed"] = True
    
    # 更新历史
    entry["last_seen"] = today_str
    entry["seen_count"] = entry.get("seen_count", 0) + 1
    
    if days_since_first <= 2:
        return "persistent"
    else:
        return "stale"


# ========== P4: 波动率分级 & 动态仓位 ==========
def calc_volatility(closes):
    """计算30日年化波动率"""
    if len(closes) < 21:
        return 0
    returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    daily_vol = (sum((r - sum(returns)/len(returns))**2 for r in returns) / len(returns)) ** 0.5
    annual_vol = daily_vol * (252 ** 0.5)
    return round(annual_vol * 100, 1)


def adjust_position_by_volatility(signal, closes):
    """
    根据板块波动率动态调整仓位：
    - 低波动(<15%): 1.2倍仓位（更安全，可以多买）
    - 中波动(15-25%): 标准仓位
    - 高波动(>25%): 0.7倍仓位（风险大，少买）
    """
    vol = calc_volatility(closes)
    base_position = signal.get("position", 500)
    
    if vol < 15:
        adjusted = int(base_position * 1.2)
        grade = "low"
        grade_label = "低波动"
    elif vol <= 25:
        adjusted = base_position
        grade = "medium"
        grade_label = "中波动"
    else:
        adjusted = int(base_position * 0.7)
        grade = "high"
        grade_label = "高波动"
    
    # 底限200，上限5000
    adjusted = max(200, min(adjusted, 5000))
    
    signal["volatility"] = vol
    signal["vol_grade"] = grade
    signal["vol_label"] = grade_label
    signal["position"] = adjusted
    signal["position_raw"] = base_position
    signal["position_note"] = f"波动率{vol}%→{grade_label}，仓位{base_position}→{adjusted}" if adjusted != base_position else ""
    
    return signal


# ========== 东方财富API ==========
def fetch_eastmoney_kline(secid, count=60, max_retries=2):
    """获取日K线数据（带重试）"""
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "end": "20500101",
        "lmt": str(count),
    }
    full_url = url + "?" + urllib.parse.urlencode(params)
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                time.sleep(1.5)
            req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
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
            else:
                return []
        except Exception as e:
            if attempt < max_retries:
                continue
            print(f"  [ERROR] {e}")
    return []


def fetch_concept_board_list():
    """获取东方财富概念板块列表(用于查找BK代码)"""
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "500", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:90+t:3",
        "fields": "f2,f3,f4,f12,f14",
    }
    full_url = url + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("data") and data["data"].get("diff"):
            return {item["f14"]: item["f12"] for item in data["data"]["diff"]}
    except Exception as e:
        print(f"  [WARN] Board list fetch failed: {e}")
    return {}


def search_c_funds(board_name):
    """搜索板块对应的C类基金"""
    keywords = board_name.replace("概念", "").replace("指数", "").strip()
    
    # 板块→搜索关键词映射
    keyword_map = {
        "科创芯片": "科创芯片",
        "存储芯片": "半导体存储",
        "半导体": "半导体",
        "先进封装": "半导体",
        "汽车芯片": "半导体芯片",
        "CPO": "通信",  
        "光通信": "通信",
        "算力": "云计算人工智能",
        "液冷服务器": "云计算",
        "铜缆高速连接": "通信",
        "PCB": "印制电路",
        "AI手机": "消费电子",
        "智能穿戴": "消费电子",
        "消费电子": "消费电子",
        "AI眼镜": "消费电子",
        "固态电池": "新能源电池",
        "低空经济": "高端装备",
        "人形机器人": "机器人",
        "商业航天": "军工航天",
        "创新药": "医药创新",
        "稀土永磁": "有色金属稀土",
        "数据要素": "大数据人工智能",
        "量子科技": "科技",
        "脑机接口": "医药科技",
        "数字货币": "金融科技",
    }
    search_kw = keyword_map.get(board_name, keywords)
    
    # 东方财富基金搜索API
    encoded = urllib.parse.quote(search_kw)
    url = f"http://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?callback=&m=1&key={encoded}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "http://fund.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
        
        # 解析JSONP
        if raw.startswith("("):
            raw = raw[1:]
        if raw.endswith(")"):
            raw = raw[:-1]
        
        data = json.loads(raw)
        funds = []
        if data.get("Datas"):
            for item in data["Datas"][:10]:
                code = item.get("CODE", "")
                name = item.get("NAME", "")
                fund_type = item.get("FundType", "")
                
                # 只保留C类基金
                if not code.endswith("C") and not name.endswith("C"):
                    continue
                # 排除ETF(场内)
                if "ETF" in name.upper() and "联接" not in name:
                    continue
                # 排除指数基金（优先主动型）
                
                funds.append({
                    "code": code,
                    "name": name,
                    "type": fund_type,
                })
        
        # 过滤：至少保留2只候选
        return funds[:3] if funds else []
    except Exception as e:
        print(f"    [WARN] Fund search for '{board_name}' failed: {e}")
        return []


# ========== 信号检测 ==========
def calc_ma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def detect_signals(klines, board_name):
    """检测三种快钱信号"""
    if not klines or len(klines) < 21:
        return None
    
    latest = klines[-1]
    prev = klines[-2]
    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]
    
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    change_pct = round((latest["close"] - prev["close"]) / prev["close"] * 100, 2)
    
    # 量比（近5日均量）
    avg_vol_5 = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else prev["volume"]
    vol_ratio = round(latest["volume"] / avg_vol_5, 2) if avg_vol_5 > 0 else 1.0
    
    dist_ma10 = round((latest["close"] - ma10) / ma10 * 100, 2) if ma10 else None
    
    signal = None
    
    # 🔥 放量突破：涨>2.5% + 量>1.2倍 + 站上MA10
    if change_pct >= 2.5 and vol_ratio >= 1.2 and dist_ma10 and dist_ma10 > 0:
        # 确认不是一日游：检查前3天走势
        prev_3_avg = sum(closes[-4:-1]) / 3
        signal = {
            "type": "breakout",
            "label": "🔥 放量突破",
            "strength": "high" if change_pct >= 5 else "medium",
            "position": 500 if change_pct < 5 else 800,
            "reason": f"涨{change_pct}%+量比{vol_ratio}+站上MA10",
            "stop_loss": round(latest["close"] * 0.97, 2),
            "take_profit": round(latest["close"] * 1.05, 2),
        }
    
    # 🩸 缩量止跌：连跌≥3天 + 日跌幅<1% + 量缩至50%
    elif is_consecutive_drop(klines, 3) and abs(change_pct) < 1 and vol_ratio <= 0.5:
        drop_pct = round((closes[-4] - closes[-1]) / closes[-4] * 100, 2)
        signal = {
            "type": "dip_buy",
            "label": "🩸 缩量止跌",
            "strength": "high",
            "position": min(3000, int(TOTAL_FLEXIBLE * 0.03)),
            "reason": f"连跌3天累计-{drop_pct}%，缩量企稳",
            "stop_loss": round(latest["close"] * 0.95, 2),
            "take_profit": round(latest["close"] * 1.08, 2),
        }
    
    # 💀 超跌反弹：单日跌>5% + 放量
    elif change_pct <= -5 and vol_ratio >= 1.5:
        signal = {
            "type": "oversold",
            "label": "💀 超跌反弹",
            "strength": "low",
            "position": min(500, int(TOTAL_FLEXIBLE * 0.005)),
            "reason": f"单日暴跌{change_pct}%+放量{vol_ratio}倍",
            "stop_loss": round(latest["close"] * 0.92, 2),
            "take_profit": round(latest["close"] * 1.10, 2),
        }
    
    # 🔄 轮动补涨：同大类内检查（在main中跨板块比较）
    
    if signal:
        signal["board"] = board_name
        signal["current"] = round(latest["close"], 1)
        signal["change_pct"] = change_pct
        signal["ma10"] = round(ma10, 1) if ma10 else None
        signal["ma20"] = round(ma20, 1) if ma20 else None
        signal["vol_ratio"] = vol_ratio
        signal["dist_ma10"] = dist_ma10
    
    return signal


def is_consecutive_drop(klines, days):
    """检查是否连续下跌"""
    if len(klines) < days + 1:
        return False
    for i in range(1, days + 1):
        if klines[-i]["close"] >= klines[-i-1]["close"]:
            return False
    return True


def detect_rotation(boards_data):
    """检测轮动补涨：同一大类内A涨>3%而B横盘(-1%~1%)"""
    rotations = []
    groups = {
        "半导体链": ["科创芯片", "存储芯片", "半导体", "先进封装", "汽车芯片"],
        "AI算力链": ["CPO", "光通信", "算力", "液冷服务器", "铜缆高速连接"],
        "消费电子": ["PCB", "AI手机", "智能穿戴", "消费电子", "AI眼镜"],
        "新质生产力": ["固态电池", "低空经济", "人形机器人", "商业航天"],
    }
    
    for group_name, boards in groups.items():
        leaders = []
        laggards = []
        for b in boards:
            if b in boards_data:
                chg = boards_data[b].get("change_pct", 0)
                if chg >= 3:
                    leaders.append((b, chg))
                elif -1 <= chg <= 1:
                    laggards.append((b, chg))
        
        if leaders and laggards:
            for laggard, lchg in laggards:
                rotations.append({
                    "type": "rotation",
                    "label": "🔄 轮动补涨",
                    "strength": "medium",
                    "position": 800,
                    "reason": f"{leaders[0][0]}涨{leaders[0][1]}%而{laggard}仅{lchg}%",
                    "board": laggard,
                    "group": group_name,
                    "leader_board": leaders[0][0],
                    "leader_change": leaders[0][1],
                    "laggard_change": lchg,
                })
    
    return rotations


# ========== 缓存管理 ==========
def load_cache():
    """加载K线缓存"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated": "", "boards": {}}


def save_cache(cache):
    """保存K线缓存"""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    cache["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def is_trading_day():
    """检查今天是否为A股交易日"""
    today = date.today()
    # 周末
    if today.weekday() >= 5:
        return False
    # 简单排除已知节假日（不完整，约90%准确率）
    holidays = {
        date(2026, 1, 1), date(2026, 1, 2),
        date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20),
        date(2026, 4, 6),
        date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5),
        date(2026, 6, 22),
        date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
    }
    if today in holidays:
        return False
    # 检查是否为开盘时间(9:30-15:00)
    return True


# ========== 主函数 ==========
def main(dry_run=False):
    cache = load_cache()
    positions_data = load_positions()
    signal_history = load_signal_history()
    now = datetime.now()
    
    if not is_trading_day():
        print(f"[{now.strftime('%H:%M')}] 今天非交易日，跳过扫描")
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing["is_trading_day"] = False
            existing["updated"] = now.strftime("%Y-%m-%dT%H:%M:%S+08:00")
            if not dry_run:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
        return
    
    print(f"[{now.strftime('%H:%M:%S')}] 快钱模块开始扫描 {len(BOARDS)} 个高波动板块...")
    
    boards_data = {}
    signals = []
    total_fetched = 0
    
    for board_name, secid in BOARDS.items():
        # 增量策略：先读缓存，只拉取新数据
        cached_board = cache.get("boards", {}).get(board_name, {})
        cached_dates = set(cached_board.get("dates", []))
        
        print(f"  [{board_name}] {secid}", end=" ")
        klines = fetch_eastmoney_kline(secid, count=60)
        
        if not klines or len(klines) < 2:
            print("→ 数据不足")
            continue
        
        total_fetched += 1
        latest = klines[-1]
        prev = klines[-2]
        closes = [k["close"] for k in klines]
        volumes = [k["volume"] for k in klines]
        
        ma10 = calc_ma(closes, 10)
        ma20 = calc_ma(closes, 20)
        change_pct = round((latest["close"] - prev["close"]) / prev["close"] * 100, 2)
        avg_vol_5 = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else prev["volume"]
        vol_ratio = round(latest["volume"] / avg_vol_5, 2) if avg_vol_5 > 0 else 1.0
        dist_ma10 = round((latest["close"] - ma10) / ma10 * 100, 2) if ma10 else None
        
        boards_data[board_name] = {
            "current": round(latest["close"], 1),
            "change_pct": change_pct,
            "ma10": round(ma10, 1) if ma10 else None,
            "ma20": round(ma20, 1) if ma20 else None,
            "vol_ratio": vol_ratio,
            "dist_ma10": dist_ma10,
        }
        
        # 更新缓存
        cache.setdefault("boards", {})[board_name] = {
            "last_close": latest["close"],
            "last_date": latest["date"],
            "dates": [k["date"] for k in klines[-40:]],
        }
        
        # 信号检测
        signal = detect_signals(klines, board_name)
        if signal:
            print(f"→ {signal['label']} | {change_pct:+.2f}% | 量{vol_ratio}")
            signals.append(signal)
        else:
            print(f"→ {change_pct:+.2f}% | 无信号")
        
        time.sleep(0.4)  # 避免API限流
    
    # 轮动补涨检测
    rotations = detect_rotation(boards_data)
    if rotations:
        print(f"\n  检测到 {len(rotations)} 个轮动补涨信号")
        signals.extend(rotations)
    
    # P3a: 信号新鲜度过滤
    fresh_signals = []
    stale_signals = []
    for sig in signals:
        freshness = check_signal_freshness(sig, signal_history)
        sig["freshness"] = freshness
        if freshness == "invalidated":
            print(f"  ✗ {sig['board']} {sig['label']} → 失效（方向反转）")
            continue
        if freshness == "stale":
            sig["note"] = sig.get("note", "") + " [信号已过3天，仅参考]"
            stale_signals.append(sig)
        else:
            sig["freshness_label"] = {"fresh": "🆕", "persistent": "⏳", "confirmed": "✅"}.get(freshness, "")
            fresh_signals.append(sig)
    
    # 合并：新鲜信号优先，过期信号放后面
    signals = fresh_signals + stale_signals
    
    # P4: 波动率分级动态仓位
    for sig in signals:
        board = sig["board"]
        secid = BOARDS.get(board)
        if secid and board in boards_data:
            klines = fetch_eastmoney_kline(secid, count=60)
            if klines and len(klines) >= 21:
                closes_v = [k["close"] for k in klines]
                sig = adjust_position_by_volatility(sig, closes_v)
    
    # 为信号匹配C类基金
    print(f"\n  共 {len(signals)} 个信号，开始匹配C类基金...")
    for sig in signals:
        board = sig["board"]
        funds = search_c_funds(board)
        if funds:
            # 排除用户已持仓
            funds = [f for f in funds if f["code"] not in EXISTING_HOLDINGS]
        sig["funds"] = funds if funds else []
        sig["funds_note"] = "" if funds else "⚠️ 未找到合适的C类基金，建议用养基宝/同花顺搜索"
        
        if funds:
            print(f"    {sig['label']} {board} → {funds[0]['code']} {funds[0]['name']}")
        else:
            print(f"    {sig['label']} {board} → 无合适基金")
        
        time.sleep(0.1)
    
    # ===== 申购门控：四道硬约束 =====
    # P3b: 先批量获取所有候选基金的真实估值
    all_fund_codes = []
    for sig in signals:
        if sig.get("funds"):
            all_fund_codes.append(sig["funds"][0]["code"])
    fund_estimates = batch_fetch_estimates(all_fund_codes) if all_fund_codes else {}
    
    print(f"\n{'='*60}")
    print(f"申购门控校验（PURCHASE GATE）:")
    actionable_signals = []
    blocked_signals = []
    
    for sig in signals:
        fund_code = sig["funds"][0]["code"] if sig.get("funds") else None
        if not fund_code:
            blocked_signals.append({**sig, "gate_blocked": True, "gate_reason": "无匹配C类基金"})
            continue
        
        # P3b: 使用真实基金估值
        fund_est = fund_estimates.get(fund_code)
        if fund_est:
            fund_estimate = {
                "change_pct": fund_est["change_pct"],
                "nav_estimate": fund_est["nav_estimate"],
                "update_time": fund_est["update_time"],
                "reliability": "high",
                "source": "天天基金实时估值"
            }
        else:
            board_change = sig.get("change_pct", 0)
            fund_estimate = {
                "change_pct": board_change,
                "reliability": "low",
                "source": "板块代理（估值API不可用）"
            }
        
        allowed, gate_results, gate_reason = purchase_gate(sig, fund_code, positions_data, fund_estimate)
        
        # P3a: 过期信号降仓位50%
        if allowed and sig.get("freshness") == "stale":
            sig["position"] = max(200, int(sig.get("position", 500) * 0.5))
            sig["note"] = sig.get("note", "") + f" [信号过期，仓位减半至¥{sig['position']}]"
        
        sig["gate_results"] = gate_results
        sig["gate_passed"] = allowed
        
        if allowed:
            actionable_signals.append(sig)
            print(f"  ✅ {sig['label']} {sig['board']} → {fund_code} | 门控全部通过")
        else:
            blocked_signals.append({**sig, "gate_blocked": True, "gate_reason": gate_reason})
            print(f"  ❌ {sig['label']} {sig['board']} → {fund_code} | {gate_reason}")
    
    # 如果没有通过门控的信号，给用户一个解释
    if not actionable_signals and blocked_signals:
        print(f"\n  ⚠️ 所有信号均被门控拦截，请勿盲目交易")
    
    # ===== 退出/止盈信号检测 =====
    exit_signals = []
    for fund_code, pos in positions_data.get("positions", {}).items():
        # 找到该基金对应的板块K线数据
        for board_name, secid in BOARDS.items():
            # 简单匹配：用对应板块K线
            if board_name not in boards_data:
                continue
            klines = fetch_eastmoney_kline(secid, count=60)
            if klines and len(klines) >= 21:
                exit_sig = detect_exit_signals(klines, fund_code, positions_data)
                if exit_sig:
                    exit_sig["fund_code"] = fund_code
                    exit_sig["board"] = board_name
                    exit_sig["days_held"] = get_days_held(pos["entry_date"])
                    exit_sig["entry_nav"] = pos.get("entry_nav", 0)
                    exit_sig["current_pnl"] = round(
                        (boards_data[board_name]["current"] - pos.get("entry_nav", boards_data[board_name]["current"])) 
                        / pos.get("entry_nav", boards_data[board_name]["current"]) * 100, 2
                    ) if pos.get("entry_nav") else None
                    exit_signals.append(exit_sig)
                break  # 每个基金只匹配一个板块
    
    if exit_signals:
        print(f"\n  检测到 {len(exit_signals)} 个退出信号:")
        for es in exit_signals:
            print(f"    {es['label']} {es['fund_code']} → {es['reason']}")
    
    # 按优先级排序：缩量止跌 > 突破 > 轮动 > 超跌
    priority = {"dip_buy": 0, "breakout": 1, "rotation": 2, "oversold": 3}
    actionable_signals.sort(key=lambda s: priority.get(s["type"], 9))
    
    # 计算今日建议仓位
    total_suggested = sum(s["position"] for s in actionable_signals[:5])
    
    # 构建输出
    output = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "is_trading_day": True,
        "scan_time": now.strftime("%H:%M"),
        "total_flexible": TOTAL_FLEXIBLE,
        "total_assets": TOTAL_ASSETS,
        "max_position": MAX_TOTAL_POSITION,
        "boards_scanned": total_fetched,
        "positions": positions_data["positions"],
        "total_invested": positions_data.get("total_invested", 0),
        "signals": actionable_signals,
        "blocked_signals": blocked_signals,
        "exit_signals": exit_signals,
        "summary": {
            "total_signals": len(signals),
            "actionable_signals": len(actionable_signals),
            "blocked_signals": len(blocked_signals),
            "exit_signals": len(exit_signals),
            "suggested_position_today": min(total_suggested, MAX_TOTAL_POSITION - positions_data.get("total_invested", 0)),
            "available_cash": TOTAL_FLEXIBLE - positions_data.get("total_invested", 0),
            "fee_reminder": "C类持有≥30天赎回费为0；7天内1.5%罚息，7-30天0.5%",
        },
        "fee_schedule": {
            "0-6天": "1.5% 赎回费 ❌ 绝对禁止",
            "7-29天": "0.5% 赎回费 ⚠️ 仅预期涨幅>2%可考虑",
            "30天+": "0% ✅ 自由进出",
        },
        "rule_reminder": {
            "timing": "支付宝T日15:00前下单按当日净值，15:00后按次交易日净值",
            "settlement": "T+1确认份额，T+2可赎回",
            "nav_update": "基金净值每晚约20:00更新，日内数据为板块指数估算",
            "gate_rules": {
                "gate1_rate_window": "同基金7天内追加→拦截；30天外0费率区自由操作",
                "gate2_cost_anchor": "板块涨幅≥3%→拦截追高，等阴线或回调至MA10",
                "gate3_data_consistency": "基金估算与板块指数方向矛盾→拦截，估值不可靠不下单",
                "gate4_position_limit": f"总仓位≤¥{MAX_TOTAL_POSITION}(约总资产{round(MAX_TOTAL_POSITION/TOTAL_ASSETS*100)}%)",
            }
        },
    }
    
    # 打印摘要
    print(f"\n{'='*60}")
    print(f"快钱模块扫描完成 | {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"扫描板块: {total_fetched}/{len(BOARDS)} | 原始信号: {len(signals)}")
    print(f"门控通过: {len(actionable_signals)} | 门控拦截: {len(blocked_signals)}")
    if exit_signals:
        print(f"退出信号: {len(exit_signals)}")
    if actionable_signals:
        print(f"今日建议仓位: ¥{output['summary']['suggested_position_today']:,}")
        for s in actionable_signals:
            fund_str = f" → {s['funds'][0]['code']} {s['funds'][0]['name']}" if s.get('funds') else " → 无合适基金"
            print(f"  {s['label']} {s['board']} ¥{s['position']}{fund_str}")
    else:
        print("今日无可执行信号（全部被门控拦截或市场平淡）")
    if blocked_signals:
        print(f"\n  拦截详情:")
        for b in blocked_signals[:5]:
            print(f"  ❌ {b.get('label', '?')} {b['board']} → {b.get('gate_reason', '无匹配基金')}")
    
    if not dry_run:
        save_signal_history(signal_history)
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        save_cache(cache)
        print(f"\n数据已保存: {OUTPUT_FILE}")
    else:
        print("\n[DRY RUN] 未写入文件")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
