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
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "quick_money.json")

# ========== 配置 ==========
TOTAL_FLEXIBLE = 96000  # 灵活资金总额
MAX_TOTAL_POSITION = 20000  # 快钱总仓位上限
MIN_FUND_SCALE = 0.5  # 基金最小规模(亿)，防清盘风险

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
    
    # 按优先级排序：缩量止跌 > 突破 > 轮动 > 超跌
    priority = {"dip_buy": 0, "breakout": 1, "rotation": 2, "oversold": 3}
    signals.sort(key=lambda s: priority.get(s["type"], 9))
    
    # 计算今日建议仓位
    total_suggested = sum(s["position"] for s in signals[:5])  # 最多取前5个信号
    
    # 构建输出
    output = {
        "updated": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "is_trading_day": True,
        "scan_time": now.strftime("%H:%M"),
        "total_flexible": TOTAL_FLEXIBLE,
        "max_position": MAX_TOTAL_POSITION,
        "boards_scanned": total_fetched,
        "signals": signals,
        "summary": {
            "total_signals": len(signals),
            "actionable_signals": len([s for s in signals if s.get("funds")]),
            "suggested_position_today": min(total_suggested, MAX_TOTAL_POSITION),
            "available_cash": TOTAL_FLEXIBLE - 1000,  # 1000已投
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
        },
    }
    
    # 打印摘要
    print(f"\n{'='*60}")
    print(f"快钱模块扫描完成 | {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"扫描板块: {total_fetched}/{len(BOARDS)} | 信号: {len(signals)}")
    if signals:
        print(f"今日建议仓位: ¥{output['summary']['suggested_position_today']:,}")
        for s in signals:
            fund_str = f" → {s['funds'][0]['code']} {s['funds'][0]['name']}" if s.get('funds') else " → 无合适基金"
            print(f"  {s['label']} {s['board']} ¥{s['position']}{fund_str}")
    else:
        print("今日无快钱信号")
    
    if not dry_run:
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
