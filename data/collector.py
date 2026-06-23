"""
天天基金数据采集器
从天天基金API获取基金历史净值和实时净值
"""
import requests
import json
import time
import sqlite3
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data.database import get_conn, DB_PATH

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://fund.eastmoney.com/"
}

def fetch_fund_history(code, start_date="2019-01-01", end_date=None):
    """
    从天天基金获取基金历史净值
    返回: list of dict {date, nav, acc_nav, daily_return}
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    records = []
    for page in range(1, 30):
        url = (
            f"https://api.fund.eastmoney.com/f10/lsjz"
            f"?callback=j&fundCode={code}"
            f"&pageIndex={page}&pageSize=200"
            f"&startDate={start_date}&endDate={end_date}"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            text = resp.text
            if text.startswith("j("):
                text = text[2:-1]
            data = json.loads(text)
            items = data.get("Data", {}).get("LSJZList", [])
            if not items:
                break
            for item in items:
                records.append({
                    "date": item["FSRQ"],
                    "nav": float(item["DWJZ"]),
                    "acc_nav": float(item.get("LJJZ", 0)),
                    "daily_return": float(item.get("JZZZL", 0) or 0)
                })
            time.sleep(0.3)
        except Exception as e:
            print(f"  [WARN] page {page}: {e}")
            break
    return records

def save_to_db(code, records):
    """保存净值数据到SQLite"""
    conn = get_conn()
    cursor = conn.cursor()
    inserted = 0
    for r in records:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO fund_nav (code, nav_date, nav, acc_nav, daily_return) VALUES (?, ?, ?, ?, ?)",
                (code, r["date"], r["nav"], r["acc_nav"], r["daily_return"])
            )
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"  [ERROR] insert {code} {r['date']}: {e}")
    conn.commit()
    conn.close()
    return inserted

def update_all_funds(fund_list):
    """批量更新所有基金数据"""
    results = {}
    for fund in fund_list:
        code = fund["code"]
        name = fund["name"]
        print(f"\n[{code}] {name}")
        
        # 获取历史数据（首次全量，后续增量）
        records = fetch_fund_history(code)
        if records:
            inserted = save_to_db(code, records)
            print(f"  Total: {len(records)} records, New: {inserted}")
            results[code] = {"total": len(records), "new": inserted}
        else:
            print(f"  No data fetched")
            results[code] = {"total": 0, "new": 0}
        time.sleep(1)
    return results

if __name__ == "__main__":
    import yaml
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    funds = [f for f in config["funds"] if f.get("enabled", True)]
    results = update_all_funds(funds)
    print(f"\nDone! Results: {results}")
