#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付宝资产配置回测引擎 v2.0
- 多数据源信息收集框架
- 蒙特卡洛模拟
- 定投回测
- 输出 JSON 供前端消费
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============ 资产参数（基于真实市场统计）============
ASSET_PARAMS = {
    'bond_china':   {'ret': 0.035, 'vol': 0.025, 'desc': '中国债券'},
    'bond_usd':     {'ret': 0.030, 'vol': 0.040, 'desc': '美元债券'},
    'money':        {'ret': 0.018, 'vol': 0.003, 'desc': '货币基金'},
    'qdii_nasdaq':  {'ret': 0.150, 'vol': 0.220, 'desc': '纳斯达克100'},
    'qdii_tech':    {'ret': 0.140, 'vol': 0.200, 'desc': '全球科技'},
    'qdii_sp500':   {'ret': 0.100, 'vol': 0.160, 'desc': '标普500'},
    'qdii_em':     {'ret': 0.070, 'vol': 0.180, 'desc': '新兴市场'},
}

# ============ 配置方案 ============
SCENARIOS = {
    'current':      {'name': '当前配置',    'desc': '债券72.4% + 货币26.2% + QDII 1.4%',     'alloc': {'bond': 0.724, 'money': 0.262, 'qdii': 0.014}},
    'conservative': {'name': '保守优化',    'desc': '债券65% + 货币25% + QDII 10%',         'alloc': {'bond': 0.65,  'money': 0.25,  'qdii': 0.10}},
    'balanced':     {'name': '平衡配置',    'desc': '债券50% + 货币20% + QDII 30%',         'alloc': {'bond': 0.50,  'money': 0.20,  'qdii': 0.30}},
    'growth':       {'name': '成长配置',    'desc': '债券35% + 货币15% + QDII 50%',         'alloc': {'bond': 0.35,  'money': 0.15,  'qdii': 0.50}},
    'aggressive':   {'name': '进取配置',    'desc': '债券20% + 货币10% + QDII 70%',         'alloc': {'bond': 0.20,  'money': 0.10,  'qdii': 0.70}},
}

# ============ 模拟数据生成 ============
def generate_prices(start, end, seed=42):
    np.random.seed(seed)
    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)
    prices = {}
    returns = {}

    for k, p in ASSET_PARAMS.items():
        returns[k] = np.random.normal(p['ret']/252, p['vol']/np.sqrt(252), n)

    # QDII 共同因子
    qdii_factor = np.random.normal(0, 1, n)
    for k in returns:
        if 'qdii' in k:
            returns[k] = returns[k] * 0.95 + qdii_factor * ASSET_PARAMS[k]['vol']/np.sqrt(252) * 0.3

    for k, ret in returns.items():
        prices[k] = pd.Series(100 * np.exp(np.cumsum(ret)), index=dates)
    return prices

# ============ 回测引擎 ============
class Engine:
    def __init__(self, prices, alloc):
        self.prices = prices
        self.alloc = alloc

    def run(self, sd=None, ed=None):
        rets = {}
        for k, p in self.prices.items():
            r = p.pct_change().dropna()
            if sd: r = r[r.index >= sd]
            if ed: r = r[r.index <= ed]
            rets[k] = r

        df = pd.DataFrame(rets).dropna()
        if len(df) == 0: return None

        cls = {}
        for c in ['bond', 'money', 'qdii']:
            cols = [k for k in df.columns if k.startswith(c) or (c=='bond' and k in ['bond_china','bond_usd'])]
            if cols: cls[c] = df[cols].mean(axis=1)

        cdf = pd.DataFrame(cls)
        w = pd.Series(self.alloc).reindex(cdf.columns).fillna(0)
        w = w / w.sum()
        port = (cdf * w).sum(axis=1)
        cum = (1 + port).cumprod()

        return {
            'total_return': cum.iloc[-1] - 1,
            'ann_return': (1 + port.mean())**252 - 1,
            'ann_vol': port.std() * np.sqrt(252),
            'sharpe': ((1 + port.mean())**252 - 1 - 0.02) / (port.std() * np.sqrt(252)) if port.std() > 0 else 0,
            'max_dd': ((cum - cum.expanding().max()) / cum.expanding().max()).min(),
            'win_rate': (port > 0).mean(),
            'days': len(port),
        }

# ============ 定投回测 ============
def sip_backtest(prices, key, monthly=50000, years=3):
    if key not in prices: return None
    p = prices[key]
    ed = p.index[-1]
    sd = ed - pd.DateOffset(years=years)
    p = p[p.index >= sd]
    if len(p) == 0: return None

    md = p.resample('ME').last().index
    invested = 0
    shares = 0
    for d in md:
        ap = p[p.index <= d]
        if len(ap) == 0: continue
        price = ap.iloc[-1]
        shares += monthly / price
        invested += monthly

    fv = shares * p.iloc[-1]
    ret = (fv - invested) / invested
    return {
        'asset': ASSET_PARAMS.get(key, {}).get('desc', key),
        'invested': int(invested),
        'final_value': round(float(fv), 2),
        'total_return': round(ret * 100, 2),
        'ann_return': round(((1 + ret)**(1/years) - 1) * 100, 2),
    }

# ============ 蒙特卡洛 ============
def monte_carlo(alloc, initial=707301, years=10, n=1000):
    days = years * 252
    port_ret = 0
    port_var = 0

    for c, w in alloc.items():
        if c == 'bond':
            ar = ASSET_PARAMS['bond_china']['ret']*0.6 + ASSET_PARAMS['bond_usd']['ret']*0.1 + ASSET_PARAMS['money']['ret']*0.3
            av = ASSET_PARAMS['bond_china']['vol']*0.6 + ASSET_PARAMS['bond_usd']['vol']*0.1 + ASSET_PARAMS['money']['vol']*0.3
        elif c == 'money':
            ar, av = ASSET_PARAMS['money']['ret'], ASSET_PARAMS['money']['vol']
        elif c == 'qdii':
            ar = ASSET_PARAMS['qdii_nasdaq']['ret']*0.45 + ASSET_PARAMS['qdii_tech']['ret']*0.43 + ASSET_PARAMS['qdii_sp500']['ret']*0.10 + ASSET_PARAMS['qdii_em']['ret']*0.02
            av = ASSET_PARAMS['qdii_nasdaq']['vol']*0.45 + ASSET_PARAMS['qdii_tech']['vol']*0.43 + ASSET_PARAMS['qdii_sp500']['vol']*0.10 + ASSET_PARAMS['qdii_em']['vol']*0.02
        else:
            continue
        port_ret += w * ar
        port_var += (w * av)**2

    pv = np.sqrt(port_var)
    dr, dv = port_ret/252, pv/np.sqrt(252)

    finals = []
    for _ in range(n):
        r = np.random.normal(dr, dv, days)
        finals.append(initial * np.prod(1 + r))

    finals = np.array(finals)
    return {
        'mean_final': round(float(np.mean(finals)), 2),
        'median_final': round(float(np.median(finals)), 2),
        'p5': round(float(np.percentile(finals, 5)), 2),
        'p25': round(float(np.percentile(finals, 25)), 2),
        'p75': round(float(np.percentile(finals, 75)), 2),
        'p95': round(float(np.percentile(finals, 95)), 2),
        'prob_profit': round(float(np.mean(finals > initial)) * 100, 1),
        'prob_double': round(float(np.mean(finals > initial * 2)) * 100, 1),
        'exp_ret': round(port_ret * 100, 2),
        'exp_vol': round(pv * 100, 2),
    }

# ============ 多数据源信息收集框架 ============
def collect_market_info():
    """
    信息收集框架 - 预留接口用于后续接入真实数据源
    当前返回模拟数据，后续可接入：
    - 东方财富/天天基金 API
    - Yahoo Finance
    - 新浪财经
    - 雪球
    """
    return {
        'data_sources': {
            'fund_info': 'https://fund.eastmoney.com/',
            'market_index': 'https://quote.eastmoney.com/',
            'qdii_premium': '手动监控或爬虫获取',
            'us_market': 'Yahoo Finance API',
        },
        'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'notes': '框架已搭建，后续可接入真实数据源替换模拟数据'
    }

# ============ 主程序 ============
def main():
    print("=" * 50)
    print("支付宝资产配置回测引擎 v2.0")
    print("=" * 50)

    ed = datetime(2026, 6, 23)
    sd5 = ed - timedelta(days=365*5)
    sd3 = ed - timedelta(days=365*3)
    sd1 = ed - timedelta(days=365)

    print("\n[1] 生成模拟数据...")
    p5 = generate_prices(sd5, ed, seed=42)
    p3 = generate_prices(sd3, ed, seed=43)
    p1 = generate_prices(sd1, ed, seed=44)

    print("\n[2] 配置回测...")
    results = {}
    for k, s in SCENARIOS.items():
        r5 = Engine(p5, s['alloc']).run()
        r3 = Engine(p3, s['alloc']).run()
        r1 = Engine(p1, s['alloc']).run()
        results[k] = {'info': s, '5y': r5, '3y': r3, '1y': r1}
        if r3:
            print(f"  {s['name']}: 3年收益{r3['total_return']*100:.2f}%, 夏普{r3['sharpe']:.2f}, 回撤{r3['max_dd']*100:.2f}%")

    print("\n[3] 定投回测...")
    sip = {}
    for k in ['qdii_nasdaq', 'qdii_tech', 'bond_china']:
        r = sip_backtest(p5, k)
        if r:
            sip[k] = r
            print(f"  {r['asset']}: 投入{r['invested']:,}, 终值{r['final_value']:,.0f}, 收益{r['total_return']:.2f}%")

    print("\n[4] 蒙特卡洛模拟（10年）...")
    mc = {}
    for k, s in SCENARIOS.items():
        mc[k] = monte_carlo(s['alloc'])
        print(f"  {s['name']}: 预期终值{mc[k]['mean_final']:,.0f}, 盈利概率{mc[k]['prob_profit']:.1f}%")

    print("\n[5] 信息收集框架...")
    info = collect_market_info()

    # 输出 JSON
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'portfolio': {
            'total': 707301.01,
            'alloc': {'bond': {'v': 512111.35, 'r': 72.4}, 'money': {'v': 185106.10, 'r': 26.2}, 'qdii': {'v': 10083.56, 'r': 1.4}}
        },
        'scenarios': {},
        'sip': sip,
        'monte_carlo': {},
        'market_info': info,
    }

    for k, r in results.items():
        d = {'name': r['info']['name'], 'desc': r['info']['desc'], 'alloc': r['info']['alloc']}
        for p in ['1y', '3y', '5y']:
            if r[p]:
                d[f'{p}_m'] = {
                    'tr': round(r[p]['total_return']*100, 2),
                    'ar': round(r[p]['ann_return']*100, 2),
                    'vol': round(r[p]['ann_vol']*100, 2),
                    'sharpe': round(r[p]['sharpe'], 3),
                    'dd': round(r[p]['max_dd']*100, 2),
                    'win': round(r[p]['win_rate']*100, 2),
                }
        report['scenarios'][k] = d

    for k, r in mc.items():
        report['monte_carlo'][k] = {'name': SCENARIOS[k]['name'], **r}

    with open('/data/user/work/repo/data.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n[6] 报告已保存到 data.json")
    return report

if __name__ == '__main__':
    main()
