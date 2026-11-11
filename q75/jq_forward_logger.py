# -*- coding: utf-8 -*-
"""
jq 前瞻记录器（双卡赛马：生产卡原池5 + 挑战卡宽基5，同口径 ms0.75）— 自包含版（跑在 GitHub Actions）
用法: python q75/jq_forward_logger.py
输出: q75/jq_forward_log.jsonl（append-only，同日重跑覆盖当日行，幂等）
设计: 无 jq 仓库依赖；东财直连；只读行情无下单接口；红线 SIMU 零接触。
逻辑: 记录每日 regime(510300 vs MA60) + 两卡各自 score>=0.75 的 picks
      （picks=生产卡原池5 / picks_w5=挑战卡宽基5，v0.4.2 双卡赛马）；
      满 5 个交易日后回填各 pick 的实际 fwd5 收益（前瞻验证样本累积）。
"""
import json
import os
import sys
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

sys.path.insert(0, OUT_DIR)
from _kline_source import fetch_kline_df  # noqa: E402  东财https→http→腾讯 三级降级
LINEAR_MS = 0.75
HORIZON = 5

POOL = {
    '510300.SH': '1.510300',
    '512010.SH': '1.512010',
    '512690.SH': '1.512690',
    '588170.SH': '1.588170',
    '159327.SZ': '0.159327',
}
POOL_WIDE5 = {
    '510300.SH': '1.510300',
    '510500.SH': '1.510500',
    '510880.SH': '1.510880',
    '512100.SH': '1.512100',
    '560010.SH': '1.560010',
}
W = {"mom_20": 0.35, "mom_5": 0.15, "amt_20": 0.20, "vol_20": 0.20, "bias_ma20": 0.10}
DIR = {"mom_20": "pos", "mom_5": "pos", "amt_20": "pos", "vol_20": "neg", "bias_ma20": "pos"}


def fetch_kline(secid, count=320):
    """东财 https→http→腾讯 三级降级（2026-11-11 修复东财 HTTPS 间歇断连）"""
    return fetch_kline_df(secid, count=count)


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

    # ---------- 挑战卡：宽基5 双卡赛马（主任批准 2026-11-11） ----------
    # 注意：宽基5卡必须在自己的 5 只截面内排名（截面分位口径），禁与生产卡混池——
    # 混 9 只排名就是"联合池追高集中"的迷你版（v0.4.1 扩池实验结论）。
    # 复用已有 510300 K线，仅拉缺失的 4 只。
    dfs_w5 = {sym: (dfs[sym] if sym in dfs else fetch_kline(secid))
              for sym, secid in POOL_WIDE5.items()}
    scores_w5 = score_cross_section(dfs_w5)
    picks_w5 = [{'symbol': s, 'score': v} for s, v in sorted(scores_w5.items(),
                key=lambda kv: -kv[1]) if v >= LINEAR_MS][:2]

    rec = {
        'date': today,
        'ts': datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'github-actions',
        'regime': ('L0 进攻' if px >= ma60 else 'L2 防守'),
        'bench_px': round(px, 3), 'bench_ma60': round(ma60, 3),
        'picks': picks, 'all_scores': scores,
        'picks_w5': picks_w5, 'all_scores_w5': scores_w5,
        'fwd5_filled': {},
    }

    # ---------- 回填历史 picks 的 fwd5 ----------
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding='utf-8') as f:
            logs = [json.loads(l) for l in f if l.strip()]

    filled = 0
    # 回填池字典映射：两卡标的全覆盖（old5 ∪ wide5）
    all_pools = {**POOL, **POOL_WIDE5}
    for old in logs:
        pend = [p for p in old.get('picks', []) + old.get('picks_w5', [])
                if p.get('fwd5_ret') is None]
        if not pend:
            continue
        entry_date = old['date']
        for sym, secid in all_pools.items():
            if not any(p['symbol'] == sym for p in pend):
                continue
            df = dfs_w5.get(sym)
            if df is None:
                df = dfs.get(sym)
            if df is None or entry_date not in df.index:
                continue
            idx = df.index.get_loc(entry_date)
            if idx + HORIZON < len(df):
                entry_px = float(df['close'].iloc[idx])
                exit_px = float(df['close'].iloc[idx + HORIZON])
                for pick_list in (old.get('picks', []), old.get('picks_w5', [])):
                    for p in pick_list:
                        if p['symbol'] == sym and p.get('fwd5_ret') is None:
                            p['fwd5_ret'] = round(exit_px / entry_px - 1, 5)
                            p['exit_date'] = df.index[idx + HORIZON].strftime('%Y-%m-%d')
                            filled += 1
        still_pending = [p for p in old.get('picks', []) + old.get('picks_w5', [])
                         if p.get('fwd5_ret') is None]
        if old.get('picks') and old.get('picks_w5') is not None:
            # 双卡记录：两卡都回填完才算满
            if not still_pending:
                old['fwd5_filled'] = True
        elif not any(p.get('fwd5_ret') is None for p in old.get('picks', [])):
            old['fwd5_filled'] = True

    # 幂等：替换当日已有记录
    logs = [l for l in logs if l.get('date') != today]
    logs.append(rec)
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        for l in logs:
            f.write(json.dumps(l, ensure_ascii=False) + '\n')

    print(f"记录 {today}: regime={rec['regime']} picks={len(picks)} "
          f"(w5={len(picks_w5)}) | 累计 {len(logs)} 天, 本轮回填 {filled} 笔")
    if not picks:
        print("  → 今日生产卡无达标 picks（宁缺毋滥空仓）")
    if not picks_w5:
        print("  → 今日挑战卡(宽基5)无达标 picks")


if __name__ == '__main__':
    main()
