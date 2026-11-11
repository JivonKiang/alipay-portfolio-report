# -*- coding: utf-8 -*-
"""
JIVONLAB 75%胜率执行器（WO-20261109-HUB-30）
用法: python q75_executor.py [--params q75_best_params.json]
输出: q75_signal.json（当日信号）+ q75_trades.json（纸面账本）
设计: 无持仓状态依赖，仅凭账本判断在市标的；信号幂等（同日重复跑结果一致）
"""
import json
import os
import sys
import urllib.request
import ssl
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kline_source import fetch_kline_df  # noqa: E402  东财https→http→腾讯 三级降级

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/126.0'}

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
PARAMS_FILE = os.path.join(OUT_DIR, 'q75_best_params.json')
SIGNAL_FILE = os.path.join(OUT_DIR, 'q75_signal.json')
TRADES_FILE = os.path.join(OUT_DIR, 'q75_trades.json')
LEDGER_FILE = os.path.join(OUT_DIR, 'q75_ledger.json')   # 模拟资金曲线（总账）

POOL = {
    '510300.SH': '1.510300',
    '510500.SH': '1.510500',
    '512100.SH': '1.512100',
    '588000.SH': '1.588000',
    '512480.SH': '1.512480',
    '515000.SH': '1.515000',
    '512690.SH': '1.512690',
    '518880.SH': '1.518880',
}


def fetch_kline(secid, beg='20240101', end='20500101'):
    """东财 https→http→腾讯 三级降级（2026-11-11 修复东财 HTTPS 间歇断连）"""
    return fetch_kline_df(secid, count=800)


def load_state():
    ledger = {'cash': 100000.0, 'history': []}
    positions = {}   # sym -> {entry_px, entry_date, shares}
    closed = []
    if os.path.exists(LEDGER_FILE):
        ledger = json.load(open(LEDGER_FILE, encoding='utf-8'))
    if os.path.exists(TRADES_FILE):
        closed = json.load(open(TRADES_FILE, encoding='utf-8'))
    # 从账本重建持仓（只保留 open 状态）
    for t in ledger.get('history', []):
        if t.get('status') == 'open':
            positions[t['sym']] = {
                'entry_px': t['entry_px'],
                'entry_date': t['entry_date'],
                'shares': t['shares'],
            }
    return ledger, positions, closed


def save_state(ledger, closed):
    json.dump(ledger, open(LEDGER_FILE, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    json.dump(closed, open(TRADES_FILE, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)


def main():
    today = date.today().isoformat()
    params = json.load(open(PARAMS_FILE, encoding='utf-8'))['best_params']
    tp = params['tp'] / 100.0
    sl = params['sl'] / 100.0
    hold = params['hold']

    ledger, positions, closed = load_state()

    # 拉全部标的最新行情
    dfs = {}
    for sym, secid in POOL.items():
        dfs[sym] = fetch_kline(secid)

    latest_day = max(df.index[-1] for df in dfs.values()).date().isoformat()

    # ---------- 1) 先处理持仓的离场 ----------
    actions = []
    for sym in list(positions):
        pos = positions[sym]
        df = dfs[sym]
        # 用最新一根 bar 检查止盈止损
        last = df.iloc[-1]
        prev = df.iloc[-2]
        entry_px = pos['entry_px']
        # 盘中价按最新收盘近似（信号生成于收盘后/次日开盘前）
        px = float(last['close'])
        days_held = len(df.loc[pos['entry_date']:]) - 1 if pos['entry_date'] in df.index else hold
        reason = None
        if px / entry_px - 1 <= -sl:
            reason = 'sl'
        elif px / entry_px - 1 >= tp:
            reason = 'tp'
        elif days_held >= hold:
            reason = 'expire'
        if reason:
            exit_px = px
            pnl = (exit_px / entry_px - 1) * pos['shares'] * entry_px
            ledger['cash'] += pos['shares'] * exit_px
            rec = {
                'sym': sym, 'entry_date': pos['entry_date'], 'exit_date': latest_day,
                'entry_px': entry_px, 'exit_px': exit_px,
                'ret': exit_px / entry_px - 1, 'reason': reason,
                'pnl': round(pnl, 2), 'status': 'closed',
            }
            closed.append(rec)
            ledger['history'] = [h for h in ledger['history']
                                 if not (h['sym'] == sym and h['status'] == 'open')]
            del positions[sym]
            actions.append(f'CLOSE {sym} @{exit_px:.3f} ({reason}, ret={rec["ret"]:+.2%})')

    # ---------- 2) 无持仓标的中找新入场 ----------
    held_syms = set(positions)
    open_slots = 3 - len(positions)     # 并发最多 3 标的
    if open_slots > 0:
        closes_above_ma = []
        for sym, df in dfs.items():
            if sym in held_syms:
                continue
            p_ma = params['ma_n']
            ma = df['close'].rolling(p_ma).mean().iloc[-1]
            px = float(df['close'].iloc[-1])
            if px > ma:
                closes_above_ma.append((sym, px, ma))
        # 入场条件按参数复现（dip/break/both）
        candidates = []
        for sym, px, ma in closes_above_ma:
            df = dfs[sym]
            delta = df['close'].diff()
            up = delta.clip(lower=0).rolling(params['rsi_n']).mean()
            dn = (-delta.clip(upper=0)).rolling(params['rsi_n']).mean()
            rsi = float(100 - 100 / (1 + (up / dn.replace(0, pd.NA))).iloc[-1])
            ret_n = float(df['close'].pct_change(params['wr_n']).iloc[-1])
            hh = float(df['high'].rolling(params['break_n']).max().shift(1).iloc[-1])
            hit_dip = rsi < params['rsi_max'] and ret_n < 0
            hit_break = px > hh
            ok = (hit_dip or hit_break) if params['entry'] in ('dip', 'break') \
                else (hit_dip or hit_break)
            if ok:
                candidates.append((sym, px, rsi))
        # 按当日动量排序取前 open_slots
        candidates.sort(key=lambda x: x[1], reverse=True)
        for sym, px, rsi in candidates[:open_slots]:
            budget = ledger['cash'] / max(open_slots, 1)
            shares = int(budget / px / 100) * 100   # A股整手
            if shares < 100:
                continue
            positions[sym] = {'entry_px': px, 'entry_date': latest_day, 'shares': shares}
            ledger['cash'] -= shares * px
            ledger['history'].append({
                'sym': sym, 'entry_date': latest_day, 'entry_px': px,
                'shares': shares, 'status': 'open',
            })
            actions.append(f'BUY {sym} @{px:.3f} x{shares} (rsi={rsi:.0f})')

    # ---------- 3) 组装信号 ----------
    pos_value = sum(p['shares'] * float(dfs[s]['close'].iloc[-1])
                    for s, p in positions.items())
    total = ledger['cash'] + pos_value
    wins = [t for t in closed if t['ret'] > 0]
    wr = len(wins) / len(closed) if closed else None

    signal = {
        'date': today,
        'data_day': latest_day,
        'params': params,
        'actions': actions,
        'positions': {s: {'entry_px': p['entry_px'], 'entry_date': p['entry_date'],
                          'shares': p['shares'],
                          'last_px': float(dfs[s]['close'].iloc[-1]),
                          'unrealized': float(dfs[s]['close'].iloc[-1]) / p['entry_px'] - 1}
                      for s, p in positions.items()},
        'cash': round(ledger['cash'], 2),
        'total_value': round(total, 2),
        'closed_trades': len(closed),
        'win_rate': round(wr, 4) if wr is not None else None,
        'pool': list(POOL),
    }
    json.dump(signal, open(SIGNAL_FILE, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    save_state(ledger, closed)

    print(json.dumps(signal, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
