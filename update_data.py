#!/usr/bin/env python3
"""
综合面板数据更新脚本
从同花顺thsdk拉取A股板块行情，计算MA10/MA20/信号，更新data.json
用法: python3 update_data.py
依赖: thsdk, pandas
"""
import json
import os
import sys
from datetime import datetime, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")

# ========== 监控配置 ==========
SECTOR_CONFIG = {
    "semiconductor": {
        "name": "半导体设备",
        "index": "科创50",
        "index_code": "000688",
        "funds": [
            {"code": "017811", "name": "东方人工智能主题混合C", "note": "重仓半导体设备，今年+104%"},
            {"code": "020357", "name": "华夏半导体材料设备ETF联接C", "note": "被动跟踪，费率更低"}
        ],
        "action_type": "auto_dca",
        "action_detail": "设每周四定投 200-500元",
        "action_path": "支付宝 → 理财 → 基金 → 搜代码 → 定投",
        "trigger": None
    },
    "pcb": {
        "name": "PCB/HDI板",
        "index": "PCB概念",
        "index_code": "BK0877",
        "funds": [
            {"code": "017811", "name": "东方人工智能主题混合C", "note": "替代方案-覆盖PCB上游设备"},
            {"code": "006373", "name": "国富全球科技互联混合", "note": "QDII-含美股PCB龙头"}
        ],
        "action_type": "wait",
        "action_detail": "等成交额缩至今日60%且跌幅收窄至1%以内再考虑",
        "action_path": None,
        "trigger": "PCB成交额 < 1400亿 且 日跌幅 < 1%"
    },
    "cpo": {
        "name": "CPO/光模块",
        "index": "CPO概念",
        "index_code": "CPO",
        "funds": [
            {"code": "017811", "name": "东方人工智能主题混合C", "note": "替代-科创50成分含CPO龙头"},
            {"code": "006373", "name": "国富全球科技互联混合", "note": "QDII-含英伟达链"}
        ],
        "action_type": "wait",
        "action_detail": "等龙头缩量止跌 + 10日线走平再考虑",
        "action_path": None,
        "trigger": "天孚通信/中际旭创 日跌幅 < 2% 且成交额缩至前日50%"
    },
    "a500": {
        "name": "中证500",
        "index": "中证500",
        "index_code": "000905",
        "funds": [
            {"code": "001557", "name": "万家中证500增强C", "note": "已设智能定投（周四）"}
        ],
        "action_type": "auto_dca",
        "action_detail": "检查智能定投是否激活（历史累计为0）",
        "action_path": "支付宝 → 理财 → 基金 → 我的定投 → 检查状态",
        "trigger": None
    }
}


def fetch_from_thsdk():
    """方案A: 同花顺thsdk数据源"""
    try:
        import thsdk
        import pandas as pd
        
        results = {}
        index_codes = {
            "semiconductor": "000688.SH",  # 科创50
            "pcb": "BK0877.SH",            # PCB概念
            "a500": "000905.SH",           # 中证500
        }
        
        for key, code in index_codes.items():
            df = thsdk.get_kline(code, ktype="day", count=30)
            if df is not None and len(df) > 0:
                latest = df.iloc[-1]
                ma10 = df["close"].rolling(10).mean().iloc[-1]
                ma20 = df["close"].rolling(20).mean().iloc[-1]
                
                change_pct = (latest["close"] - df.iloc[-2]["close"]) / df.iloc[-2]["close"] * 100
                dist_ma10 = (latest["close"] - ma10) / ma10 * 100
                
                results[key] = {
                    "current": round(latest["close"], 1),
                    "ma10": round(ma10, 1) if pd.notna(ma10) else -1,
                    "ma20": round(ma20, 1) if pd.notna(ma20) else -1,
                    "change_pct": round(change_pct, 2),
                    "distance_ma10": round(dist_ma10, 2),
                    "volume_ratio": round(latest["volume"] / df["volume"].iloc[-2], 2) if len(df) > 1 else None
                }
        
        # CPO - 用中际旭创(300308)作为代理
        df_cpo = thsdk.get_kline("300308.SZ", ktype="day", count=30)
        if df_cpo is not None and len(df_cpo) > 0:
            latest = df_cpo.iloc[-1]
            change_pct = (latest["close"] - df_cpo.iloc[-2]["close"]) / df_cpo.iloc[-2]["close"] * 100
            results["cpo"] = {
                "current": -1,
                "ma10": -1,
                "ma20": -1,
                "change_pct": round(change_pct, 2),
                "distance_ma10": -1,
                "volume_ratio": round(latest["volume"] / df_cpo["volume"].iloc[-2], 2) if len(df_cpo) > 1 else None
            }
        
        return results
    
    except ImportError:
        print("[WARN] thsdk not installed, trying CSV fallback")
        return None
    except Exception as e:
        print(f"[WARN] thsdk error: {e}, trying CSV fallback")
        return None


def fetch_from_csv():
    """方案B: 从fund-trend-system的CSV缓存读取"""
    import pandas as pd
    
    results = {}
    
    csv_map = {
        "semiconductor": "000688_科创50.csv",
        "a500": "000905_中证500.csv",
    }
    
    for key, filename in csv_map.items():
        path = f"../../github_repos/fund-trend-system/data/index_data/{filename}"
        try:
            df = pd.read_csv(path)
            if len(df) > 0:
                latest = df.iloc[-1]
                ma10 = df["close"].rolling(10).mean().iloc[-1]
                ma20 = df["close"].rolling(20).mean().iloc[-1]
                change_pct = (latest["close"] - df.iloc[-2]["close"]) / df.iloc[-2]["close"] * 100
                dist_ma10 = (latest["close"] - ma10) / ma10 * 100
                
                results[key] = {
                    "current": round(latest["close"], 1),
                    "ma10": round(ma10, 1) if pd.notna(ma10) else -1,
                    "ma20": round(ma20, 1) if pd.notna(ma20) else -1,
                    "change_pct": round(change_pct, 2),
                    "distance_ma10": round(dist_ma10, 2),
                    "volume_ratio": None
                }
        except FileNotFoundError:
            results[key] = {"current": -1, "ma10": -1, "ma20": -1, "change_pct": 0, "distance_ma10": -1, "volume_ratio": None}
    
    return results


def determine_signal(sector_data, sector_key):
    """基于技术指标判断买卖信号"""
    dist = sector_data.get("distance_ma10", -1)
    change = sector_data.get("change_pct", 0)
    vol_ratio = sector_data.get("volume_ratio")

    if dist == -1:
        return "avoid", "数据缺失，手动判断"

    # 放量暴跌 → avoid
    if change < -3 and vol_ratio and vol_ratio > 0.8:
        return "avoid", f"放量暴跌{change}%，等缩量止跌"
    
    # 缩量暴跌 → watch (恐慌盘减少)
    if change < -3 and vol_ratio and vol_ratio < 0.7:
        return "watch", f"缩量回调{change}%，接近买点，盯缩量止跌"
    
    # 跌幅较大且远离10日线 → avoid
    if dist < -5:
        return "avoid", f"远离10日线{dist:.1f}%，趋势破坏"
    
    # 接近10日线且缩量 → watch
    if -3 < dist < 0 and change > -2:
        return "watch", f"距10日线{dist:.1f}%，接近支撑"
    
    # 站上10日线 → buy/dca
    if dist > 0:
        return "dca", f"站上10日线+{dist:.1f}%，定投正常执行"
    
    # 默认
    return "watch", f"距10日线{dist:.1f}%，观望"


def update_data_json():
    """主函数：拉取数据并更新data.json"""
    
    # 读取现有data.json作为模板
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 尝试方案A: thsdk
    sector_data = fetch_from_thsdk()
    
    # 方案B: CSV fallback
    if sector_data is None or len(sector_data) < 2:
        print("[INFO] Falling back to CSV data source")
        csv_data = fetch_from_csv()
        if sector_data is None:
            sector_data = csv_data
        else:
            # 合并（thsdk优先）
            for k, v in csv_data.items():
                if k not in sector_data or sector_data[k].get("current", -1) == -1:
                    sector_data[k] = v
    
    # 填充信号
    for key, cfg in SECTOR_CONFIG.items():
        if key in sector_data:
            sd = sector_data[key]
            signal, signal_text = determine_signal(sd, key)
            
            data["sectors"][key]["current"] = sd["current"]
            data["sectors"][key]["ma10"] = sd["ma10"]
            data["sectors"][key]["ma20"] = sd["ma20"]
            data["sectors"][key]["change_pct"] = sd["change_pct"]
            data["sectors"][key]["distance_ma10"] = sd.get("distance_ma10", -1)
            data["sectors"][key]["volume_ratio"] = sd.get("volume_ratio")
            data["sectors"][key]["signal"] = signal
            data["sectors"][key]["signal_text"] = signal_text
    
    # 更新时间戳
    data["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    
    # 写回
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] data.json updated at {data['updated']}")
    
    # 打印今日信号
    print("\n=== 今日板块信号 ===")
    for key, s in data["sectors"].items():
        print(f"  {s['name']}: {s['signal'].upper()} - {s['signal_text']}")
    
    return data


if __name__ == "__main__":
    update_data_json()
