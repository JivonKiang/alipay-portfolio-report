#!/usr/bin/env python3
"""
同花顺纳指ETF数据采集脚本
由 GitHub Actions 定时运行，配合 update-cache.js 使用
获取国内纳指ETF实时行情，用于折溢价监控
"""

import json
import os
import sys
import time
from thsdk import THS

# ===== 配置 =====
# 纳指ETF列表（THSCODE）
NASDAQ_ETF_CODES = {
    "USHJ513300": "纳斯达克ETF华夏",
    "USHJ513110": "纳指ETF华泰柏瑞",
    "USHJ513870": "纳指ETF富国",
    "USHJ513390": "纳指100ETF博时",
    "USZJ159513": "纳斯达克100ETF大成",
    "USZJ159632": "纳斯达克ETF华安",
    "USZJ159659": "纳斯达克100ETF招商",
    "USZJ159501": "纳指ETF嘉实",
}

# 纳指指数 THSCODE
NDX_THS_CODE = "UNQQNDAQ"

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ths-cache.json")


def fetch_etf_data(ths, code, name):
    """获取单只ETF行情"""
    prefix = code[:4]
    try:
        if prefix in ("USHJ", "USZJ"):
            resp = ths.market_data_cn(code, "汇总")
        else:
            resp = ths.market_data_us(code, "基础数据")

        if not resp or not resp.data:
            return None

        row = resp.data[0]
        return {
            "code": code,
            "name": name,
            "price": row.get("价格"),
            "open": row.get("开盘价"),
            "high": row.get("最高价"),
            "low": row.get("最低价"),
            "prev_close": row.get("昨收价"),
            "change_pct": row.get("涨跌幅") or row.get("涨幅"),
            "volume": row.get("成交量"),
            "amount": row.get("总金额"),
            "turnover_rate": row.get("换手率"),
            "amplitude": row.get("振幅"),
        }
    except Exception as e:
        print(f"  ⚠️ {name} ({code}) 获取失败: {e}", file=sys.stderr)
        return None


def fetch_ndx_index(ths):
    """获取纳斯达克指数行情（同花顺侧）"""
    try:
        resp = ths.market_data_us(NDX_THS_CODE, "基础数据")
        if not resp or not resp.data:
            return None
        row = resp.data[0]
        return {
            "code": NDX_THS_CODE,
            "name": "纳斯达克",
            "price": row.get("价格"),
            "prev_close": row.get("昨收价"),
            "open": row.get("开盘价"),
            "high": row.get("最高价"),
            "low": row.get("最低价"),
        }
    except Exception as e:
        print(f"  ⚠️ 纳指指数获取失败: {e}", file=sys.stderr)
        return None


def main():
    print("开始采集同花顺纳指ETF数据...")

    result = {
        "timestamp": int(time.time() * 1000),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataSource": "thsdk",
        "etfs": [],
        "ndx_index": None,
    }

    try:
        with THS() as ths:
            # 采集纳指指数
            result["ndx_index"] = fetch_ndx_index(ths)
            time.sleep(0.3)

            # 采集各ETF
            for code, name in NASDAQ_ETF_CODES.items():
                etf_data = fetch_etf_data(ths, code, name)
                if etf_data:
                    result["etfs"].append(etf_data)
                time.sleep(0.3)

            # 计算折溢价（如果同时有ETF价格和实际纳指点位）
            # 注：纳指ETF净值需要从Yahoo Finance侧获取，这里先只采集原始数据
            # 折溢价计算放在 update-cache.js 中完成

    except Exception as e:
        print(f"❌ 同花顺数据采集失败: {e}", file=sys.stderr)
        result["error"] = str(e)

    # 写入输出文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    etf_count = len(result["etfs"])
    print(f"✅ 同花顺数据采集完成！共获取 {etf_count} 只纳指ETF数据")
    if result["etfs"]:
        for e in result["etfs"]:
            print(f"   {e['name']}: ¥{e['price']} ({e['change_pct'] or 'N/A'})")


if __name__ == "__main__":
    main()
