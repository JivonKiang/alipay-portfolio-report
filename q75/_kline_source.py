# -*- coding: utf-8 -*-
"""
K线数据源公共模块（2026-11-11 修复：东财 HTTPS 间歇断连 RemoteDisconnected）
三级降级链:
  1. 东财 push2his HTTPS (原通道)
  2. 东财 push2his HTTP  (明文端口, TLS 层被掐时的逃生口; 板块码 90.BKxxxx 仅此源可用)
  3. 腾讯 web.ifzq.gtimg.cn qfq (ETF/指数备源; 板块码不支持)
字段口径: 与东财 fqt=1 前复权对齐 (2026-11-11 实测 60 bar max rel diff = 0.0)
单位口径: 东财 vol=手, 腾讯 volume=手 (同单位直用); amt 东财=元, 腾讯无 → 0
"""
import json
import re
import ssl
import time
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/126.0'}

_TX_PREFIX = {'1': 'sh', '0': 'sz'}


def _fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def _em_kline_df(secid, count):
    """东财通道 (https→http 降级)，返回 DataFrame 或 None"""
    import pandas as pd
    base = (
        'https://push2his.eastmoney.com/api/qt/stock/kline/get?'
        f'secid={secid}&fields1=f1,f2,f3,f4,f5&'
        'fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=1'
        '&beg=20240101&end=20500101'
    )
    for scheme in ('https', 'http'):
        try:
            d = _fetch(base.replace('https://push2his', scheme + '://push2his', 1))
            rows = [r.split(',') for r in d['data']['klines']]
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'vol', 'amt'])
            for c in ['open', 'close', 'high', 'low', 'vol', 'amt']:
                df[c] = pd.to_numeric(df[c])
            df['date'] = pd.to_datetime(df['date'])
            return df.set_index('date').iloc[-count:]
        except Exception:
            time.sleep(1.0)
    return None


def _tx_kline_df(secid, count):
    """腾讯备源，返回 DataFrame 或 None。板块码(90.BKxxxx)不支持。"""
    import pandas as pd
    if secid.startswith('90.'):
        return None
    m = re.match(r'^([10])\.(\d{6})$', secid)
    if not m:
        return None
    code = _TX_PREFIX[m.group(1)] + m.group(2)
    # count>800 时腾讯上限兜不住，东财20240101起全量也约≤800，直接取800
    n = min(count, 800)
    url = (f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'
           f'param={code},day,,,{n},qfq')
    try:
        d = _fetch(url)
        node = d['data'][code]
        rows = node.get('qfqday') or node.get('day') or []
        if not rows:
            return None
        df = pd.DataFrame(
            [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), 0.0]
             for r in rows],
            columns=['date', 'open', 'close', 'high', 'low', 'vol', 'amt'])
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date').iloc[-count:]
    except Exception:
        return None


def fetch_kline_df(secid, count=320):
    """统一入口: 东财(https→http) → 腾讯。全败抛 RuntimeError。"""
    err = None
    try:
        df = _em_kline_df(secid, count)
        if df is not None and len(df):
            return df
    except Exception as e:  # noqa: BLE001
        err = e
    df = _tx_kline_df(secid, count)
    if df is not None and len(df):
        return df
    raise RuntimeError(f'all sources failed for {secid}: {err}')
