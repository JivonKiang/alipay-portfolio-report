#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
右侧交易每日扫描器（MACD + KDJ）
================================
- 每个交易日北京时间 14:10 由 GitHub Actions 定时触发
- 扫描范围：东方财富全部概念板块 + 行业板块 + 主流宽基指数
- 右侧交易筛选条件（三条同时满足才达标）：
  1. MACD 红柱 > 10 且 DIF > DEA（金叉状态）
  2. K > D（KDJ 金叉状态，未死叉）
  3. K < 90 且 J < 100（未进超买区，仍有上涨空间）
- 输出：scan/data.json（GitHub Pages 面板 /scan/index.html 读取）
"""
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 输出到仓库根 scan/ 目录（GitHub Pages 从 main 根部署 → 面板地址 /scan/）
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "scan")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
}

# ---------- 筛选参数 ----------
HIST_MIN = 10.0      # MACD 红柱下限
K_MAX = 90.0         # K 上限（未超买）
J_MAX = 100.0        # J 上限（未超买）
KLINE_BARS = 140     # 计算指标所需 K 线根数

# ---------- ETF 映射（板块/指数 → 支付宝可搜的场内 ETF；场外需搜「XXETF联接」） ----------
# 覆盖常用标的，未列出的可在支付宝直接搜索板块关键词，可自行增删
INDEX_ETF_MAP = {
    "上证指数": "510210 上证综指ETF",
    "上证50": "510050 上证50ETF",
    "沪深300": "510300 沪深300ETF",
    "中证500": "510500 中证500ETF",
    "中证1000": "512100 中证1000ETF",
    "创业板指": "159915 创业板ETF",
    "科创50": "588000 科创50ETF",
    "深证成指": "159901 深100ETF",
    "北证50": "",
}
SECTOR_ETF_MAP = {
    # 申万一级行业（31个）
    "半导体": "512480 半导体ETF", "电子": "159997 电子ETF", "计算机": "512720 计算机ETF",
    "通信": "515880 通信ETF", "传媒": "512980 传媒ETF", "数字媒体": "512980 传媒ETF",
    "电力设备": "516320 电力设备ETF", "机械设备": "", "国防军工": "512660 军工ETF",
    "汽车": "516110 汽车ETF", "医药生物": "512010 医药ETF", "食品饮料": "515170 食品饮料ETF",
    "农林牧渔": "159825 农业ETF", "银行": "512800 银行ETF", "非银金融": "512000 券商ETF",
    "房地产": "512200 房地产ETF", "煤炭": "515220 煤炭ETF", "石油石化": "561360 石油石化ETF",
    "基础化工": "159870 化工ETF", "钢铁": "515210 钢铁ETF", "有色金属": "512400 有色ETF",
    "建筑材料": "159745 建材ETF", "建筑装饰": "516970 基建ETF", "家用电器": "159996 家电ETF",
    "纺织服饰": "", "轻工制造": "", "商业贸易": "", "商贸零售": "",
    "社会服务": "159766 旅游ETF", "综合": "", "公用事业": "159611 电力ETF",
    "交通运输": "561320 交通运输ETF", "环保": "512580 环保ETF", "美容护理": "",
    # 常见概念板块
    "人工智能": "159819 AI ETF", "AI算力": "159819 AI ETF", "算力租赁": "159819 AI ETF",
    "光伏": "515790 光伏ETF", "光伏主材": "515790 光伏ETF", "光伏设备": "515790 光伏ETF",
    "锂电池": "561910 锂电池ETF", "新能源车": "515030 新能源车ETF", "充电桩": "159695 充电桩ETF",
    "机器人": "562500 机器人ETF", "减速器": "562500 机器人ETF",
    "券商": "512000 券商ETF", "证券": "512000 券商ETF", "保险": "512070 证券保险ETF",
    "白酒": "512690 酒ETF", "酿酒": "512690 酒ETF", "啤酒": "512690 酒ETF",
    "医疗": "512170 医疗ETF", "医疗器械": "512170 医疗ETF", "化学制药": "512010 医药ETF",
    "生物制品": "512010 医药ETF", "中药": "560080 中药ETF", "创新药": "159992 创新药ETF",
    "游戏": "159869 游戏ETF", "影视动漫制作": "512980 传媒ETF", "影视院线": "512980 传媒ETF",
    "消费电子": "159732 消费电子ETF", "苹果概念": "159732 消费电子ETF", "消费电子零部件及组装": "159732 消费电子ETF",
    "军工": "512660 军工ETF", "地面兵装Ⅲ": "512660 军工ETF", "航天航空": "512660 军工ETF",
    "黄金": "518880 黄金ETF", "贵金属": "518880 黄金ETF", "稀土": "516150 稀土ETF",
    "存储芯片": "512480 半导体ETF", "芯片": "159995 芯片ETF",
    "PCB": "159667 PCB ETF", "印制电路板": "159667 PCB ETF",
    "氢能源": "159668 氢能ETF",
    "数据中心": "516510 大数据ETF", "云计算": "516510 大数据ETF", "大数据": "516510 大数据ETF",
    "物联网": "159895 物联网ETF", "车联网": "159895 物联网ETF",
    "养殖": "159825 农业ETF", "种植业": "159825 农业ETF", "线下药店": "512010 医药ETF",
    "旅游": "159766 旅游ETF", "酒店餐饮": "159766 旅游ETF", "免税": "159766 旅游ETF",
    "煤炭开采": "515220 煤炭ETF", "电力": "159611 电力ETF", "电网": "159611 电力ETF",
    "工程建设": "516970 基建ETF", "水泥": "159745 建材ETF", "玻璃玻纤": "159745 建材ETF",
}

# 主流宽基指数（secid, 名称）
BROAD_INDEXES = [
    ("1.000001", "上证指数"),
    ("0.399001", "深证成指"),
    ("1.000300", "沪深300"),
    ("1.000905", "中证500"),
    ("1.000852", "中证1000"),
    ("1.000016", "上证50"),
    ("0.399006", "创业板指"),
    ("1.000688", "科创50"),
    ("0.899050", "北证50"),
]


def http_json(url, timeout=12, retries=3):
    """带重试的 JSON 请求，失败返回 None（失败隔离）"""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception:
            if i < retries - 1:
                time.sleep(1 + i)
    return None


def _f(v, default=0.0):
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def fetch_sector_list(fs_type, label):
    """拉取东财板块列表（分页）。fs_type: '2'=概念板块, '1'=行业板块"""
    out, pn = [], 1
    while pn <= 15:
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get?pn={pn}&pz=100&po=1&np=1"
            f"&fltt=2&invt=2&fid=f12&fs=m:90+t:{fs_type}&fields=f3,f12,f14"
        )
        data = http_json(url)
        diff = (data or {}).get("data") or {}
        items = diff.get("diff") or []
        if not items:
            break
        for it in items:
            code = it.get("f12", "")
            if code.startswith("BK"):
                out.append({
                    "secid": f"90.{code}",
                    "name": it.get("f14", code),
                    "change_pct": _f(it.get("f3")),
                    "type": label,
                })
        total = diff.get("total") or 0
        if len(out) >= total:
            break
        pn += 1
    return out


def fetch_kline(secid, lmt=KLINE_BARS):
    """拉取日线 K 线，返回 dict 或 None"""
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}"
        f"&klt=101&fqt=1&lmt={lmt}&end=20500101"
        f"&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55"
    )
    data = http_json(url)
    kl = (data or {}).get("data") or {}
    rows = kl.get("klines") or []
    if len(rows) < 60:
        return None
    dates, closes, highs, lows = [], [], [], []
    for row in rows:
        parts = row.split(",")
        dates.append(parts[0])
        closes.append(_f(parts[2]))
        highs.append(_f(parts[3]))
        lows.append(_f(parts[4]))
    return {"name": kl.get("name", ""), "dates": dates, "close": closes, "high": highs, "low": lows}


# ---------- 指标计算（纯 Python，无第三方依赖） ----------
def ema(series, span):
    a = 2.0 / (span + 1)
    out = [series[0]]
    for x in series[1:]:
        out.append(a * x + (1 - a) * out[-1])
    return out


def sma_cn(series, n=3, m=1):
    """通达信 SMA(X,N,M): Y = (M*X + (N-M)*Y') / N"""
    a = m / n
    out = [series[0]]
    for x in series[1:]:
        out.append(a * x + (1 - a) * out[-1])
    return out


def calc_indicators(close, high, low):
    """返回最新一根的 dif, dea, hist(红柱), k, d, j"""
    n = len(close)
    # MACD
    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    dif_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    dea_line = ema(dif_line, 9)
    hist = 2.0 * (dif_line[-1] - dea_line[-1])
    # KDJ（9 日 RSV）
    period = 9
    rsv_series = []
    for i in range(n):
        if i < period - 1:
            rsv_series.append(50.0)
            continue
        hn = max(high[i - period + 1: i + 1])
        ln = min(low[i - period + 1: i + 1])
        rsv_series.append(50.0 if hn == ln else (close[i] - ln) / (hn - ln) * 100.0)
    k_line = sma_cn(rsv_series, 3, 1)
    d_line = sma_cn(k_line, 3, 1)
    j_val = 3.0 * k_line[-1] - 2.0 * d_line[-1]
    return {
        "dif": dif_line[-1],
        "dea": dea_line[-1],
        "hist": hist,
        "k": k_line[-1],
        "d": d_line[-1],
        "j": j_val,
    }


def lookup_etf(name, ttype):
    """板块/指数 → 对应 ETF（支付宝可直接搜索的场内代码）"""
    if ttype == "宽基指数":
        return INDEX_ETF_MAP.get(name, "")
    return SECTOR_ETF_MAP.get(name, "")


def evaluate(target):
    """评估单个板块/指数，返回结果 dict 或 None（失败跳过）"""
    kl = fetch_kline(target["secid"])
    if not kl:
        return None
    try:
        ind = calc_indicators(kl["close"], kl["high"], kl["low"])
    except Exception:
        return None
    dif, dea, hist = ind["dif"], ind["dea"], ind["hist"]
    k, d, j = ind["k"], ind["d"], ind["j"]

    fails = []
    if not (hist > HIST_MIN):
        fails.append(f"红柱{hist:.1f}≤10")
    if not (dif > dea):
        fails.append("DIF≤DEA")
    if not (k > d):
        fails.append("K≤D死叉")
    if not (k < K_MAX and j < J_MAX):
        fails.append("KDJ超买")

    passed = len(fails) == 0
    near = (not passed) and dif > dea and k > d and hist > 0  # 观察池：多头排列但红柱不足或接近超买

    return {
        "secid": target["secid"],
        "name": target["name"] or kl.get("name", ""),
        "type": target["type"],
        "etf": lookup_etf(target["name"] or kl.get("name", ""), target["type"]),
        "close": kl["close"][-1],
        "change_pct": target.get("change_pct", 0.0),
        "dif": round(dif, 2),
        "dea": round(dea, 2),
        "hist": round(hist, 2),
        "k": round(k, 2),
        "d": round(d, 2),
        "j": round(j, 2),
        "passed": passed,
        "near": near,
        "fails": fails,
    }


def scan_all():
    now_bj = datetime.now(timezone(timedelta(hours=8)))
    print(f"[{now_bj:%Y-%m-%d %H:%M:%S}] 开始扫描 ...")

    # 1. 汇总扫描目标
    targets = [{"secid": s, "name": n, "type": "宽基指数", "change_pct": 0.0} for s, n in BROAD_INDEXES]
    concepts = fetch_sector_list("2", "概念板块")
    industries = fetch_sector_list("1", "行业板块")
    targets += concepts + industries
    print(f"目标数：指数 {len(BROAD_INDEXES)} + 概念 {len(concepts)} + 行业 {len(industries)}")

    # 2. 并发扫描（8 线程，单只失败不影响整体）
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(evaluate, t): t for t in targets}
        done = 0
        for fut in as_completed(futures):
            done += 1
            if done % 100 == 0:
                print(f"  进度 {done}/{len(targets)}")
            try:
                r = fut.result()
            except Exception:
                continue
            if r:
                results.append(r)

    passed = [r for r in results if r["passed"]]
    near = [r for r in results if r["near"]]
    passed.sort(key=lambda x: -x["hist"])
    near.sort(key=lambda x: -x["hist"])
    idx_passed = [r["name"] for r in passed if r["type"] == "宽基指数"]

    data = {
        "generated_at": now_bj.strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": now_bj.strftime("%Y-%m-%d"),
        "rules": {
            "macd": f"MACD 红柱 > {HIST_MIN:g} 且 DIF > DEA",
            "kdj": "K > D（金叉状态未死叉）",
            "room": f"K < {K_MAX:g} 且 J < {J_MAX:g}（未超买，仍有上涨空间）",
        },
        "summary": {
            "scanned": len(results),
            "failed_fetch": len(targets) - len(results),
            "passed": len(passed),
            "near": len(near),
            "index_passed": idx_passed,
        },
        "passed": passed,
        "near": near,
        "all": sorted(results, key=lambda x: (x["type"], -x["hist"])),
    }

    # 3. 落盘
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"完成：扫描 {len(results)}，达标 {len(passed)}，观察 {len(near)}")
    print(f"达标指数：{idx_passed or '无'}")
    return data


if __name__ == "__main__":
    scan_all()
