# -*- coding: utf-8 -*-
"""
q75/em_fetch.py — 东财/腾讯双源 K 线拉取（CI 用，自包含）
2026-11-11: 东财开始掐数据中心 IP（GitHub Actions Azure 段 RemoteDisconnected），
            主源失败自动降级腾讯 ifzq（jq 网关同款端点，10/10 标的验证通过）。
返回 DataFrame: date 索引 + open/close/high/low/vol/amt 数值列。
只读行情，无下单接口。
"""
import json
import time
import urllib.request
import ssl

import pandas as pd

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/126.0'}

EM_HOSTS = ['push2his.eastmoney.com', '92.push2his.eastmoney.com']


def _em_secid(code: str) -> str:
    """'510300' → '1.510300'（SH）/'0.510300'（SZ）。"""
    if code.endswith('.SH'):
        return '1.' + code[:-3]
    if code.endswith('.SZ'):
        return '0.' + code[:-3]
    return ('1.' if code[0] in '569' else '0.') + code


def _tx_code(code: str) -> str:
    """'510300.SH' → 'sh510300'。"""
    if code.endswith('.SH'):
        return 'sh' + code[:-3]
    if code.endswith('.SZ'):
        return 'sz' + code[:-3]
    return ('sh' if code[0] in '569' else 'sz') + code


def _fetch_em(secid: str):
    """东财 push2his 主源（多主机重试）。"""
    url = ('https://push2his.eastmoney.com/api/qt/stock/kline/get?'
           f'secid={secid}&fields1=f1,f2,f3,f4,f5&'
           'fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1'
           '&beg=20240101&end=20500101')
    last_err = None
    for i, host in enumerate(EM_HOSTS * 2):
        try:
            req = urllib.request.Request(url.replace('push2his.eastmoney.com', host, 1),
                                         headers=UA)
            d = json.load(urllib.request.urlopen(req, timeout=20, context=CTX))
            rows = [r.split(',') for r in d['data']['klines']]
            df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high',
                                             'low', 'vol', 'amt'])
            for c in ['open', 'close', 'high', 'low', 'vol', 'amt']:
                df[c] = pd.to_numeric(df[c])
            df['date'] = pd.to_datetime(df['date'])
            return df.set_index('date')
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (i + 1))
    raise last_err


def _fetch_tx(code: str, count: int = 320):
    """腾讯 ifzq 降级源（jq 网关同款端点，格式归一到东财列）。"""
    c = _tx_code(code)
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'
           f'param={c},day,,,{count + 1},qfq')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    d = json.loads(urllib.request.urlopen(req, timeout=20, context=CTX).read().decode())
    data = d['data'][c]
    key = 'qfqday' if 'qfqday' in data else 'day'
    # 腾讯行: [date, open, close, high, low, volume, ...]（ amount 缺失用 vol*close 近似）
    rows = data[key]
    df = pd.DataFrame([r[:6] for r in rows],
                      columns=['date', 'open', 'close', 'high', 'low', 'vol'])
    for c_ in ['open', 'close', 'high', 'low', 'vol']:
        df[c_] = pd.to_numeric(df[c_])
    df['amt'] = df['vol'] * df['close']  # 近似成交额（打分口径只用作截面分位，同源一致即可）
    df['date'] = pd.to_datetime(df['date'])
    return df.set_index('date').iloc[-count:]


def fetch_kline(code: str, count: int = 320) -> pd.DataFrame:
    """双源拉取：东财主源 → 腾讯降级。code 形如 '510300.SH'。"""
    try:
        df = _fetch_em(_em_secid(code))
        if len(df):
            return df.iloc[-count:]
        raise RuntimeError('eastmoney empty')
    except Exception:
        return _fetch_tx(code, count)
