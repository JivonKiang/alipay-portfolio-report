"""
Portfolio Engine - 每日持仓净值更新 + 资产总览
数据源: 天天基金(primary) + 东方财富(fallback) + 新浪(tertiary)
输出: portfolio_data.json → GitHub Pages 面板直接读取
"""
import json
import os
import urllib.request
import urllib.parse
import time
from datetime import datetime, date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 输出到工作区 output 目录（与 index.html 同级）
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)  # temp/ 的父目录 = workspace/
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "portfolio_data.json")
POSITIONS_FILE = os.path.join(SCRIPT_DIR, "positions.json")

# ========== 配置 ==========
TOTAL_FLEXIBLE = 96000
TOTAL_MONEY_FUND = 50000
TOTAL_ASSETS = TOTAL_FLEXIBLE + TOTAL_MONEY_FUND
EXISTING_HOLDINGS = {"005844", "006503", "025209"}

# 基金持仓信息
FUND_INFO = {
    "005844": {"name": "东方人工智能主题混合C", "type": "科技成长", "sub_type": "AI/半导体"},
    "006503": {"name": "财通集成电路产业股票C", "type": "科技成长", "sub_type": "PCB/集成电路"},
    "025209": {"name": "永赢先锋半导体智选混合C", "type": "科技成长", "sub_type": "存储芯片"},
}


def fetch_fund_nav_ttjj(fund_code):
    """天天基金：净值历史（多页）"""
    url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize=5"
    headers = {"Referer": "https://fund.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data.get("ErrCode") == 0 and data.get("Data", {}).get("LSJZList"):
                return data["Data"]["LSJZList"]
        except:
            time.sleep(1)
    return []


def fetch_fund_nav_sina(fund_code):
    """新浪基金净值（fallback）"""
    url = f"https://stock.finance.sina.com.cn/fundInfo/api/openapi.php/CaihuiFundInfoService.getNav?symbol={fund_code}&page=1"
    headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get("result_code") == "0" and data.get("result", {}).get("list"):
            return data["result"]["list"]
    except:
        pass
    return []


def fetch_with_retry(url, headers, max_retries=3):
    """带指数退避的请求"""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
            else:
                raise e
    return {}


def fetch_market_breadth():
    """市场状态：四大指数 + 两市成交额"""
    indices = {
        "上证指数": "1.000001",
        "深证成指": "0.399001",
        "创业板指": "0.399006",
        "科创50": "1.000688",
    }
    secids = ",".join(indices.values())
    url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f2,f3,f6,f12,f14&secids={secids}&_={int(time.time()*1000)}"
    headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
    
    result = {"indices": {}, "volume_total": 0, "market_state": "unknown"}
    try:
        data = fetch_with_retry(url, headers)
        if data.get("data", {}).get("diff"):
            total_volume = 0
            for item in data["data"]["diff"]:
                code = item.get("f12", "")
                for name, sid in indices.items():
                    if code == sid.split(".")[-1]:
                        change_pct = round(item.get("f3", 0), 2)
                        volume = item.get("f6", 0) or 0
                        total_volume += volume
                        result["indices"][name] = {
                            "current": round(item.get("f2", 0), 2),
                            "change_pct": change_pct,
                            "volume_yi": round(volume / 1e8, 1),
                        }
            
            up_count = sum(1 for v in result["indices"].values() if v.get("change_pct", 0) > 0)
            down_count = sum(1 for v in result["indices"].values() if v.get("change_pct", 0) < 0)
            result["volume_total"] = round(total_volume / 1e8, 1)
            
            if up_count == 4:
                result["market_state"] = "risk_on"
                result["state_label"] = "强多"
            elif up_count >= 3:
                result["market_state"] = "bullish"
                result["state_label"] = "偏多"
            elif down_count >= 3:
                result["market_state"] = "bearish"
                result["state_label"] = "偏空"
            elif down_count == 4:
                result["market_state"] = "risk_off"
                result["state_label"] = "强空"
            else:
                result["market_state"] = "neutral"
                result["state_label"] = "震荡"
    except Exception as e:
        result["error"] = str(e)[:40]
    
    result["update_time"] = datetime.now().strftime("%H:%M")
    return result


def fetch_industry_rotation():
    """概念板块当日涨跌Top/Bottom 5"""
    headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
    try:
        url_up = f"https://push2.eastmoney.com/api/qt/clist/get?fid=f3&po=1&pz=5&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f3,f14&_={int(time.time()*1000)}"
        up_data = fetch_with_retry(url_up, headers)
        top = [{"name": d.get("f14",""), "change_pct": round(d.get("f3",0),2)} 
               for d in up_data.get("data",{}).get("diff",[])]
        
        url_down = f"https://push2.eastmoney.com/api/qt/clist/get?fid=f3&po=0&pz=5&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f3,f14&_={int(time.time()*1000)}"
        down_data = fetch_with_retry(url_down, headers)
        bottom = [{"name": d.get("f14",""), "change_pct": round(d.get("f3",0),2)} 
                  for d in down_data.get("data",{}).get("diff",[])]
        return top, bottom
    except:
        return [], []


def calculate_portfolio():
    """主函数：计算完整持仓状态"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Portfolio Engine start...")
    
    # 加载持仓
    positions_data = {}
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, "r") as f:
            positions_data = json.load(f)
    
    positions = positions_data.get("positions", {})
    history_trades = positions_data.get("history", [])
    
    # 获取每只基金的最新净值
    portfolio_holdings = []
    total_market_value = 0
    total_profit = 0
    
    for fund_code, pos in positions.items():
        # 尝试天天基金API
        nav_records = fetch_fund_nav_ttjj(fund_code)
        if not nav_records:
            nav_records = fetch_fund_nav_sina(fund_code)
        
        latest_nav = None
        last_nav_date = None
        if nav_records:
            # LSJZList 格式: [{"FSRQ":"2026-06-24","DWJZ":"3.5592","LJJZ":"..."}, ...]
            latest = nav_records[0]
            latest_nav = float(latest.get("DWJZ", 0))
            last_nav_date = latest.get("FSRQ", "")
        
        # 获取实时估值（天天基金fundgz）
        fund_est = None
        try:
            url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js?rt={int(time.time()*1000)}"
            req = urllib.request.Request(url, headers={"Referer": "https://fund.eastmoney.com/"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode()
            start = text.index("{")
            end = text.rindex("}") + 1
            est_data = json.loads(text[start:end])
            fund_est = {
                "nav_estimate": float(est_data.get("gsz", 0)),
                "change_pct": float(est_data.get("gszzl", 0)),
                "update_time": est_data.get("gztime", ""),
            }
        except:
            pass
        
        entry_nav = pos.get("entry_nav", latest_nav or 0)
        entry_amount = pos.get("amount", 0)
        entry_date = pos.get("entry_date", "")
        
        # 根据最新净值计算盈亏（优先用日内估值）
        if fund_est and fund_est["nav_estimate"] > 0:
            nav_final = fund_est["nav_estimate"]
            nav_source = "estimate"
        elif latest_nav:
            nav_final = latest_nav
            nav_source = "confirmed"
        else:
            nav_final = entry_nav
            nav_source = "entry"
        
        shares = entry_amount / entry_nav if entry_nav > 0 else 0
        current_value = shares * nav_final
        profit = current_value - entry_amount
        profit_pct = (profit / entry_amount * 100) if entry_amount > 0 else 0
        
        # 持有天数
        days_held = 0
        if entry_date:
            try:
                entry_dt = datetime.strptime(entry_date, "%Y-%m-%d").date()
                days_held = (date.today() - entry_dt).days
            except:
                pass
        
        info = FUND_INFO.get(fund_code, {"name": fund_code, "type": "未知", "sub_type": ""})
        
        holding = {
            "code": fund_code,
            "name": info["name"],
            "type": info["type"],
            "sub_type": info["sub_type"],
            "entry_nav": round(entry_nav, 4),
            "entry_amount": entry_amount,
            "entry_date": entry_date,
            "latest_nav": round(nav_final, 4),
            "nav_date": last_nav_date or "",
            "shares": round(shares, 2),
            "current_value": round(current_value, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2),
            "days_held": days_held,
            "fee_tier": "0%" if days_held >= 30 else ("0.5%" if days_held >= 7 else "1.5%"),
            "estimate": fund_est,
        }
        portfolio_holdings.append(holding)
        total_market_value += current_value
        total_profit += profit
    
    # 市场宽度
    breadth = fetch_market_breadth()
    
    # 行业轮动
    top_industries, bottom_industries = fetch_industry_rotation()
    
    # 费率提醒
    fee_checks = []
    for h in portfolio_holdings:
        if h["days_held"] < 7:
            fee_checks.append(f"{h['name'][:8]}持有{h['days_held']}天，赎回费1.5%")
        elif h["days_held"] < 30:
            fee_checks.append(f"{h['name'][:8]}持有{h['days_held']}天，赎回费0.5%")
    
    # 构建输出
    output = {
        "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "is_trading_day": True,
        "total_assets": {
            "flexible_cash": TOTAL_FLEXIBLE,
            "money_fund": TOTAL_MONEY_FUND,
            "invested": round(total_market_value, 2),
            "total": round(TOTAL_FLEXIBLE + TOTAL_MONEY_FUND + total_market_value, 2),
        },
        "portfolio": {
            "holdings": portfolio_holdings,
            "count": len(portfolio_holdings),
            "total_invested": round(sum(p["entry_amount"] for p in portfolio_holdings), 2),
            "total_market_value": round(total_market_value, 2),
            "total_profit": round(total_profit, 2),
            "total_profit_pct": round(total_profit / sum(p["entry_amount"] for p in portfolio_holdings) * 100, 2) if portfolio_holdings else 0,
            "available_cash": TOTAL_FLEXIBLE - sum(p["entry_amount"] for p in portfolio_holdings),
        },
        "market_breadth": breadth,
        "industry_rotation": {
            "top": top_industries,
            "bottom": bottom_industries,
        },
        "warnings": [],
        "fee_checks": fee_checks,
    }
    
    # 风险告警
    for h in portfolio_holdings:
        if h["profit_pct"] < -10:
            output["warnings"].append({
                "level": "danger",
                "msg": f"{h['name'][:10]}亏损{h['profit_pct']:.1f}%，接近止损线-12%"
            })
        elif h["profit_pct"] > 15:
            output["warnings"].append({
                "level": "info",
                "msg": f"{h['name'][:10]}盈利{h['profit_pct']:.1f}%，可考虑止盈30%"
            })
    
    # 写入
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # 历史曲线：追加今日快照到 positions_value_history.json
    history_file = os.path.join(OUTPUT_DIR, "positions_value_history.json")
    snapshots = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                snapshots = json.load(f)
        except:
            pass
    today_str = date.today().strftime("%Y-%m-%d")
    # 去重：同一天只留最后一个快照
    snapshots = [s for s in snapshots if s.get("date") != today_str]
    snapshots.append({
        "date": today_str,
        "total_value": round(total_market_value, 2),
        "total_profit": round(total_profit, 2),
        "total_profit_pct": round(total_profit / sum(p["entry_amount"] for p in portfolio_holdings) * 100, 2) if portfolio_holdings else 0,
        "holdings_count": len(portfolio_holdings),
        "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    })
    # 只保留最近90天
    snapshots = snapshots[-90:]
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, ensure_ascii=False, indent=2)
    
    print(f"  Holdings: {len(portfolio_holdings)} | P&L: ¥{total_profit:+.2f} | Market cap: ¥{round(total_market_value, 2)}")
    print(f"  Output: {OUTPUT_FILE}")
    return output


if __name__ == "__main__":
    calculate_portfolio()
