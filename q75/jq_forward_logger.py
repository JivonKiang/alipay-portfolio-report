# -*- coding: utf-8 -*-
"""
jq 前瞻记录器（生产池线性卡 ms0.75）— 自包含版（跑在 GitHub Actions）
用法: python q75/jq_forward_logger.py
输出: q75/jq_forward_log.jsonl（append-only，同日重跑覆盖当日行，幂等）
设计: 无 jq 仓库依赖；东财直连；只读行情无下单接口；红线 SIMU 零接触。
逻辑: 记录每日 regime(510300 vs MA60) + 线性卡 score>=0.75 的 picks；
      满 5 个交易日后回填各 pick 的实际 fwd5 收益（前瞻验证样本累积）。
"""
import json
import os
import urllib.request
import ssl
from datetime import datetime, timezone, timedelta

import pandas as pd

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/126.0'}

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(OUT_DIR, 'jq_forward_log.jsonl')
LINEAR_MS = 0.75
HORIZON = 5

POOL = {
    '510300.SH': '1.510300',
    '512010.SH': '1.512010',
    '512690.SH': '1.512690',
    '588170.SH': '1.588170',
    '159327.SZ': '0.159327',
}
W = {"mom_20": 0.35, "mom_5": 0.15, "amt_20": 0.20, "vol_20": 0.20, "bias_ma20": 0.10}
DIR = {"mom_20": "pos", "mom_5": "pos", "amt_20": "pos", "vol_20": "neg", "bias_ma20": "pos"}


def fetch_kline(secid, count=320):
    url = (
        'https://push2his.eastmoney.com/api/qt/stock/kline/get?'
        f'secid={secid}&fields1=f1,f2,f3,f4,f5&'
        'fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1'
        '&beg=20240101&end=20500101'
    )
    req = urllib.request.Request(url, headers=UA)
    d = json.load(urllib.request.urlopen(req, timeout=20, context=CTX))
    rows = [r.split(',') for r in d['data']['klines']]
    df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol', 'amt'])
    for c in ['open', 'close', 'high', 'low', 'vol', 'amt']:
        df[c] = pd.to_numeric(df[c])
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    return df.iloc[-count:]


def factor_row(df):
    """单标的因子行（与 jq alpha.registry 同口径）。df 含 close/volume，索引为日期。"""
    c, v = df['close'], df['vol']   # 东财 kline 列名为 vol
    return {
        'mom_20': c.iloc[-1] / c.iloc[-21] - 1,
        'mom_5': c.iloc[-1] / c.iloc[-6] - 1,
        'vol_20': c.pct_change().rolling(20).std().iloc[-1] * (252 ** 0.5),
        'amt_20': (c * v).rolling(20).mean().iloc[-1] / 1000,
        'bias_ma20': c.iloc[-1] / c.rolling(20).mean().iloc[-1] - 1,
    }


def score_cross_section(dfs):
    """截面打分（与 jq alpha.scorecard 同口径：每因子截面分位 0~1 加权）。"""
    rows = {sym: factor_row(df) for sym, df in dfs.items()}
    syms = list(rows)
    scores = {}
    for name in W:
        raw = pd.Series({s: rows[s][name] for s in syms})
        r = raw.rank(pct=True)
        if DIR[name] == 'neg':
            r = 1.0 - r
        r = r.fillna(0.0)
        for s in syms:
            scores[s] = scores.get(s, 0.0) + W[name] * float(r[s])
    return {s: round(v, 4) for s, v in scores.items()}


def main():
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    dfs = {sym: fetch_kline(secid) for sym, secid in POOL.items()}

    bench = dfs['510300.SH']['close']
    ma60 = float(bench.rolling(60).mean().iloc[-1])
    px = float(bench.iloc[-1])

    scores = score_cross_section(dfs)
    picks = [{'symbol': s, 'score': v} for s, v in sorted(scores.items(),
             key=lambda kv: -kv[1]) if v >= LINEAR_MS][:2]

    rec = {
        'date': today,
        'ts': datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'github-actions',
        'regime': ('L0 进攻' if px >= ma60 else 'L2 防守'),
        'bench_px': round(px, 3), 'bench_ma60': round(ma60, 3),
        'picks': picks, 'all_scores': scores,
        'fwd5_filled': {},
    }

    # ---------- 回填历史 picks 的 fwd5 ----------
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding='utf-8') as f:
            logs = [json.loads(l) for l in f if l.strip()]

    filled = 0
    for old in logs:
        pend = [p for p in old.get('picks', []) if p.get('fwd5_ret') is None]
        if not pend:
            continue
        entry_date = old['date']
        for sym, secid in POOL.items():
            if not any(p['symbol'] == sym for p in pend):
                continue
            df = dfs[sym]
            if entry_date not in df.index:
                continue
            idx = df.index.get_loc(entry_date)
            if idx + HORIZON < len(df):
                entry_px = float(df['close'].iloc[idx])
                exit_px = float(df['close'].iloc[idx + HORIZON])
                for p in old['picks']:
                    if p['symbol'] == sym:
                        p['fwd5_ret'] = round(exit_px / entry_px - 1, 5)
                        p['exit_date'] = df.index[idx + HORIZON].strftime('%Y-%m-%d')
                        filled += 1
        if not any(p.get('fwd5_ret') is None for p in old.get('picks', [])):
            old['fwd5_filled'] = True

    # 幂等：替换当日已有记录
    logs = [l for l in logs if l.get('date') != today]
    logs.append(rec)
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        for l in logs:
            f.write(json.dumps(l, ensure_ascii=False) + '\n')

    print(f"记录 {today}: regime={rec['regime']} picks={len(picks)} | "
          f"累计 {len(logs)} 天, 本轮回填 {filled} 笔")
    if not picks:
        print("  → 今日无达标 picks（宁缺毋滥空仓）")


if __name__ == '__main__':
    main()
