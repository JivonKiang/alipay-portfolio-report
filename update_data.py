#!/usr/bin/env python3
"""
综合面板数据更新脚本 v2
数据源: 东方财富免费API（无需登录/无需安装非标准库）
计算MA10/MA20/信号，更新data.json

用法:
  python3 update_data.py            # 更新data.json
  python3 update_data.py --dry-run  # 只打印信号，不写文件

定时执行:
  GitHub Actions: cron "0 3,5 * * 1-5" (北京时间11:00和13:00)
  或元宝定时触发 Marvis 执行此脚本
"""
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, date
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")

# ========== 监控配置 ==========
# 板块→东财指数代码映射
SECTOR_INDEX_MAP = {
    "semiconductor": {"code": "1.000688", "name": "科创50"},
    "pcb":           {"code": "90.BK0877", "name": "PCB概念"},
    "a500":          {"code": "1.000905", "name": "中证500"},
}

# CPO代理：中际旭创 300308
CPO_PROXY = {"code": "0.300308", "name": "中际旭创(CPO代理)"}

FUNDS_MAP = {
    "semiconductor": [
        {"code": "017811", "name": "东方人工智能主题混合C", "note": "重仓半导体设备，今年+104%"},
        {"code": "020357", "name": "华夏半导体材料设备ETF联接C", "note": "被动跟踪，费率更低"}
    ],
    "pcb": [
        {"code": "017811", "name": "东方人工智能主题混合C", "note": "替代方案-覆盖PCB上游设备"},
        {"code": "006373", "name": "国富全球科技互联混合", "note": "QDII-含美股PCB龙头"}
    ],
    "cpo": [
        {"code": "017811", "name": "东方人工智能主题混合C", "note": "替代-科创50成分含CPO龙头"},
        {"code": "006373", "name": "国富全球科技互联混合", "note": "QDII-含英伟达链"}
    ],
    "a500": [
        {"code": "001557", "name": "万家中证500增强C", "note": "已设智能定投（周四）"}
    ],
}

ACTION_CONFIG = {
    "auto_dca": {"type": "auto_dca", "detail": "设每周四定投 200-500元", "path": "支付宝 → 理财 → 基金 → 搜代码 → 定投"},
    "wait": {"type": "wait", "detail": "等缩量止跌再考虑"},
}


def fetch_eastmoney_kline(secid, count=30):
    """
    东方财富K线API
    secid格式: "1.000688" (上证指数) 或 "0.300308" (深证个股) 或 "90.BK0877" (板块)
    返回: list[dict] 包含 date, open, close, high, low, volume, amount
    """
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",       # 日K
        "fqt": "1",         # 前复权
        "end": "20500101",
        "lmt": str(count),
    }
    full_url = url + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
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
        print(f"  [ERR] fetch {secid}: {e}")
    return []


def calc_ma(values, period):
    """计算移动平均"""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def determine_signal(change_pct, dist_ma10, vol_ratio):
    """基于技术指标判断买卖信号"""
    if dist_ma10 is None:
        return "avoid", "数据缺失，手动判断"

    volume = vol_ratio if vol_ratio is not None else 1.0

    # 放量或正常量能的大跌，先规避，避免把下跌中继误判为买点
    if change_pct <= -3 and volume >= 0.8:
        return "avoid", f"放量暴跌{change_pct}%，等缩量止跌"

    # 缩量大跌可以观察，但不直接给定投信号
    if change_pct <= -3 and volume < 0.8:
        return "watch", f"缩量回调{change_pct}%，接近买点，盯缩量止跌"

    # 中等跌幅但明显放量，通常说明分歧扩大，先等跌幅收窄
    if -3 < change_pct <= -2 and volume >= 1.2:
        return "avoid", f"放量下跌{change_pct}%，先等跌幅收窄"

    # 中等跌幅即使未放量，也不应因为站上10日线就直接给定投信号
    if -3 < change_pct <= -2:
        return "watch", f"回调{change_pct}%，观察是否缩量企稳"

    # 大幅远离10日线 → avoid
    if dist_ma10 < -5:
        return "avoid", f"远离10日线{dist_ma10:.1f}%，趋势破坏"

    # 轻微跌破10日线但跌幅很小，长期宽基定投可继续
    if -1.5 <= dist_ma10 < 0 and change_pct > -1:
        return "dca", f"距10日线{dist_ma10:.1f}%，小幅回调，定投正常执行"

    # 接近10日线但仍在下方，先观察支撑是否有效
    if -3 < dist_ma10 < 0 and change_pct > -2:
        return "watch", f"距10日线{dist_ma10:.1f}%，接近支撑"

    # 站上10日线 → dca
    if dist_ma10 > 0:
        return "dca", f"站上10日线+{dist_ma10:.1f}%，定投正常执行"

    return "watch", f"距10日线{dist_ma10:.1f}%，观望"


def update_data_json(dry_run=False):
    """主函数"""
    
    # 读取现有data.json
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    results = {}
    
    # 拉取板块数据
    for key, cfg in SECTOR_INDEX_MAP.items():
        print(f"Fetching {cfg['name']} ({cfg['code']})...")
        klines = fetch_eastmoney_kline(cfg["code"], count=30)
        if not klines or len(klines) < 2:
            print(f"  SKIP: insufficient data")
            results[key] = {"error": True}
            continue
        
        latest = klines[-1]
        prev = klines[-2]
        closes = [k["close"] for k in klines]
        volumes = [k["volume"] for k in klines]
        
        ma10 = calc_ma(closes, 10)
        ma20 = calc_ma(closes, 20)
        change_pct = round((latest["close"] - prev["close"]) / prev["close"] * 100, 2)
        dist_ma10 = round((latest["close"] - ma10) / ma10 * 100, 2) if ma10 else None
        vol_ratio = round(latest["volume"] / prev["volume"], 2) if prev["volume"] > 0 else None
        
        signal, signal_text = determine_signal(change_pct, dist_ma10, vol_ratio)
        
        results[key] = {
            "current": round(latest["close"], 1),
            "ma10": round(ma10, 1) if ma10 else -1,
            "ma20": round(ma20, 1) if ma20 else -1,
            "change_pct": change_pct,
            "distance_ma10": dist_ma10 if dist_ma10 is not None else -1,
            "volume_ratio": vol_ratio,
            "signal": signal,
            "signal_text": signal_text,
        }
        ma10_str = f"{ma10:.1f}" if ma10 else "?"
        print(f"  {latest['close']:.1f} | {change_pct:+.2f}% | MA10={ma10_str} | {signal.upper()}")

    # CPO代理
    print(f"Fetching CPO proxy ({CPO_PROXY['code']})...")
    klines = fetch_eastmoney_kline(CPO_PROXY["code"], count=30)
    if klines and len(klines) >= 2:
        latest = klines[-1]; prev = klines[-2]
        change_pct = round((latest["close"] - prev["close"]) / prev["close"] * 100, 2)
        vol_ratio = round(latest["volume"] / prev["volume"], 2) if prev["volume"] > 0 else None
        closes = [k["close"] for k in klines]
        ma10 = calc_ma(closes, 10)
        dist_ma10 = round((latest["close"] - ma10) / ma10 * 100, 2) if ma10 else None
        signal, signal_text = determine_signal(change_pct, dist_ma10, vol_ratio)
        results["cpo"] = {
            "current": round(latest["close"], 1),
            "ma10": round(ma10, 1) if ma10 else -1,
            "ma20": -1,
            "change_pct": change_pct,
            "distance_ma10": dist_ma10 if dist_ma10 is not None else -1,
            "volume_ratio": vol_ratio,
            "signal": signal,
            "signal_text": signal_text + " (中际旭创代理)",
        }
        print(f"  中际旭创 {latest['close']:.1f} | {change_pct:+.2f}% | {signal.upper()}")

    # 更新data.json
    for key in results:
        if results[key].get("error"):
            continue
        r = results[key]
        
        if key not in data["sectors"]:
            continue
        
        data["sectors"][key]["current"] = r["current"]
        data["sectors"][key]["ma10"] = r["ma10"]
        data["sectors"][key]["ma20"] = r.get("ma20", -1)
        data["sectors"][key]["change_pct"] = r["change_pct"]
        data["sectors"][key]["distance_ma10"] = r["distance_ma10"]
        data["sectors"][key]["volume_ratio"] = r.get("volume_ratio")
        data["sectors"][key]["signal"] = r["signal"]
        data["sectors"][key]["signal_text"] = r["signal_text"]
        
        # 更新操作建议
        if r["signal"] == "avoid":
            if key in ["pcb", "cpo"]:
                data["sectors"][key]["action"]["type"] = "wait"
                data["sectors"][key]["action"]["detail"] = "等缩量止跌 + 跌幅收窄至1%以内"
                data["sectors"][key]["action"]["path"] = None
        elif r["signal"] == "watch":
            if key in ["pcb", "cpo"]:
                data["sectors"][key]["action"]["type"] = "wait"
                data["sectors"][key]["action"]["detail"] = "接近支撑位，盯缩量止跌信号"
                data["sectors"][key]["action"]["path"] = None
        elif r["signal"] == "dca":
            data["sectors"][key]["action"]["type"] = "auto_dca"
            data["sectors"][key]["action"]["detail"] = "定投正常执行"
            data["sectors"][key]["action"]["path"] = "支付宝 → 理财 → 基金 → 我的定投"
    
    data["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    
    if dry_run:
        print("\n=== DRY RUN - 未写入文件 ===")
    else:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] data.json updated at {data['updated']}")
    
    # 打印信号汇总
    print("\n=== 今日板块信号 ===")
    for key in ["semiconductor", "pcb", "cpo", "a500"]:
        if key in data["sectors"]:
            s = data["sectors"][key]
            print(f"  {s['name']:8s} | {s['change_pct']:+6.2f}% | MA10距离: {s['distance_ma10']:+5.1f}% | {s['signal'].upper():6s} | {s['signal_text']}")
    
    return data


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    update_data_json(dry_run=dry_run)
