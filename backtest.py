#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付宝资产配置回测分析脚本
基于用户当前持仓，回测不同配置策略的历史表现
使用模拟数据 + 真实市场参数进行回测
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'WenQuanYi Micro Hei', 'Noto Sans CJK SC']
plt.rcParams['axes.unicode_minus'] = False

# ============ 1. 用户当前资产配置数据 ============
CURRENT_PORTFOLIO = {
    'bond': {
        'name': '稳健理财（债券为主）',
        'value': 512111.35,
        'ratio': 0.724,
        'funds': [
            {'name': '景顺长城景颐裕利债券C', 'value': 206701.83, 'ratio': 0.3295},
            {'name': '西部利得汇享债券C', 'value': 166539.49, 'ratio': 0.2655},
            {'name': '西部利得季季稳90天滚动持有债券A', 'value': 97722.98, 'ratio': 0.1558},
            {'name': '信澳稳悦60天滚动持有债券C', 'value': 40312.87, 'ratio': 0.0643},
            {'name': '华泰保兴尊睿6个月持有期债券A', 'value': 814.18, 'ratio': 0.0013},
            {'name': '易方达中短期美元债债券(QDII)A', 'value': 20.00, 'ratio': 0.0001},
        ]
    },
    'money': {
        'name': '灵活取用（货币基金）',
        'value': 185106.10,
        'ratio': 0.262,
        'funds': [
            {'name': '余额宝', 'value': 105106.10},
            {'name': '兴全天添益货币A', 'value': 80000.00},
        ]
    },
    'qdii': {
        'name': '进阶理财（QDII为主）',
        'value': 10083.56,
        'ratio': 0.014,
        'funds': [
            {'name': '易方达全球优质企业混合(QDII)A', 'value': 1111.51},
            {'name': '广发全球精选股票(QDII)A', 'value': 900.87},
            {'name': '万家纳斯达克100指数(QDII)A', 'value': 803.64},
            {'name': '银华海外数字经济量化混合(QDII)A', 'value': 800.00},
            {'name': '南方纳斯达克100指数(QDII)A', 'value': 709.50},
            {'name': '华宝致远混合(QDII)A', 'value': 645.90},
            {'name': '建信纳斯达克100指数(QDII)A', 'value': 607.29},
            {'name': '汇添富纳斯达克100ETF联接(QDII)A', 'value': 606.95},
            {'name': '嘉实全球产业升级股票(QDII)A', 'value': 554.44},
            {'name': '国富全球科技互联混合(QDII)A', 'value': 538.43},
            {'name': '摩根纳斯达克100指数(QDII)A', 'value': 531.94},
            {'name': '华夏全球科技先锋混合(QDII)A', 'value': 500.00},
            {'name': '宝盈纳斯达克100指数(QDII)A', 'value': 344.48},
            {'name': '招商纳斯达克100ETF联接(QDII)A', 'value': 343.96},
            {'name': '大成纳斯达克100ETF联接(QDII)A', 'value': 209.13},
            {'name': '易方达全球成长精选混合(QDII)A', 'value': 197.28},
            {'name': '易方达全球成长精选混合(QDII)C', 'value': 151.14},
            {'name': '摩根标普500指数(QDII)A', 'value': 148.99},
            {'name': '华安纳斯达克100ETF联接(QDII)A', 'value': 90.63},
            {'name': '广发纳斯达克100ETF联接(QDII)A', 'value': 90.50},
            {'name': '华泰柏瑞纳斯达克100ETF联接(QDII)A', 'value': 70.72},
            {'name': '建信新兴市场优选混合(QDII)A', 'value': 65.53},
            {'name': '广发纳斯达克100ETF联接(QDII)C', 'value': 60.73},
        ]
    }
}

TOTAL_ASSET = 707301.01

# ============ 2. 基于真实市场参数生成模拟数据 ============
# 使用历史统计参数（基于中国市场真实数据）
ASSET_PARAMS = {
    'bond_china_bond': {
        'annual_return': 0.035,      # 中国债券基金年化收益约3.5%
        'annual_volatility': 0.025,   # 波动率约2.5%
        'desc': '中国债券'
    },
    'bond_usd_bond': {
        'annual_return': 0.030,      # 美元债券年化约3%
        'annual_volatility': 0.040,   # 波动率约4%
        'desc': '美元债券'
    },
    'bond_money_market': {
        'annual_return': 0.018,      # 货币基金年化约1.8%
        'annual_volatility': 0.003,   # 波动率约0.3%
        'desc': '货币基金'
    },
    'money_money_market': {
        'annual_return': 0.018,
        'annual_volatility': 0.003,
        'desc': '货币基金'
    },
    'qdii_nasdaq100': {
        'annual_return': 0.150,      # 纳斯达克100年化约15%
        'annual_volatility': 0.220,   # 波动率约22%
        'desc': '纳斯达克100'
    },
    'qdii_global_tech': {
        'annual_return': 0.140,      # 全球科技年化约14%
        'annual_volatility': 0.200,   # 波动率约20%
        'desc': '全球科技'
    },
    'qdii_sp500': {
        'annual_return': 0.100,      # 标普500年化约10%
        'annual_volatility': 0.160,   # 波动率约16%
        'desc': '标普500'
    },
    'qdii_emerging': {
        'annual_return': 0.070,      # 新兴市场年化约7%
        'annual_volatility': 0.180,   # 波动率约18%
        'desc': '新兴市场'
    }
}

# 资产间相关系数矩阵（基于历史真实相关性）
CORRELATION_MATRIX = {
    ('bond_china_bond', 'bond_usd_bond'): 0.3,
    ('bond_china_bond', 'bond_money_market'): 0.1,
    ('bond_china_bond', 'qdii_nasdaq100'): -0.1,
    ('bond_china_bond', 'qdii_global_tech'): -0.1,
    ('bond_china_bond', 'qdii_sp500'): 0.0,
    ('bond_china_bond', 'qdii_emerging'): 0.1,
    ('bond_usd_bond', 'qdii_nasdaq100'): -0.2,
    ('bond_usd_bond', 'qdii_global_tech'): -0.2,
    ('bond_usd_bond', 'qdii_sp500'): -0.1,
    ('qdii_nasdaq100', 'qdii_global_tech'): 0.9,
    ('qdii_nasdaq100', 'qdii_sp500'): 0.8,
    ('qdii_nasdaq100', 'qdii_emerging'): 0.6,
    ('qdii_global_tech', 'qdii_sp500'): 0.75,
    ('qdii_global_tech', 'qdii_emerging'): 0.55,
    ('qdii_sp500', 'qdii_emerging'): 0.5,
}

def generate_simulated_prices(start_date, end_date, seed=42):
    """生成基于真实市场参数的模拟价格数据"""
    np.random.seed(seed)
    
    # 生成交易日历
    dates = pd.bdate_range(start=start_date, end=end_date)
    n_days = len(dates)
    
    prices = {}
    returns = {}
    
    # 先生成独立的收益率序列
    for key, params in ASSET_PARAMS.items():
        daily_return = params['annual_return'] / 252
        daily_vol = params['annual_volatility'] / np.sqrt(252)
        
        # 生成随机收益率
        random_returns = np.random.normal(daily_return, daily_vol, n_days)
        returns[key] = random_returns
    
    # 应用相关性（使用Cholesky分解简化处理）
    # 这里简化处理：对QDII资产添加共同因子
    common_qdii_factor = np.random.normal(0, 1, n_days)
    
    for key in returns:
        if 'qdii' in key:
            # QDII资产受共同因子影响
            factor_loading = 0.3
            returns[key] = returns[key] * np.sqrt(1 - factor_loading**2) + \
                          common_qdii_factor * ASSET_PARAMS[key]['annual_volatility'] / np.sqrt(252) * factor_loading
    
    # 转换为价格序列
    for key, ret in returns.items():
        price_series = 100 * np.exp(np.cumsum(ret))
        prices[key] = pd.Series(price_series, index=dates)
    
    return prices

# ============ 3. 建议配置方案 ============
PROPOSED_SCENARIOS = {
    'current': {
        'name': '当前配置',
        'desc': '债券72.4% + 货币26.2% + QDII 1.4%',
        'allocation': {'bond': 0.724, 'money': 0.262, 'qdii': 0.014}
    },
    'conservative': {
        'name': '保守优化',
        'desc': '债券65% + 货币25% + QDII 10%',
        'allocation': {'bond': 0.65, 'money': 0.25, 'qdii': 0.10}
    },
    'balanced': {
        'name': '平衡配置',
        'desc': '债券50% + 货币20% + QDII 30%',
        'allocation': {'bond': 0.50, 'money': 0.20, 'qdii': 0.30}
    },
    'growth': {
        'name': '成长配置',
        'desc': '债券35% + 货币15% + QDII 50%',
        'allocation': {'bond': 0.35, 'money': 0.15, 'qdii': 0.50}
    },
    'aggressive': {
        'name': '进取配置',
        'desc': '债券20% + 货币10% + QDII 70%',
        'allocation': {'bond': 0.20, 'money': 0.10, 'qdii': 0.70}
    }
}

# ============ 4. 回测引擎 ============
class BacktestEngine:
    def __init__(self, prices, allocation, initial_value=100000):
        self.prices = prices
        self.allocation = allocation
        self.initial_value = initial_value
        self.results = {}
        
    def run_backtest(self, start_date=None, end_date=None):
        """运行回测"""
        portfolio_returns = self._calculate_portfolio_returns(start_date, end_date)
        if portfolio_returns is None or len(portfolio_returns) == 0:
            return None
            
        cumulative = (1 + portfolio_returns).cumprod()
        
        self.results = {
            'returns': portfolio_returns,
            'cumulative': cumulative,
            'total_return': cumulative.iloc[-1] - 1,
            'annualized_return': self._annualized_return(portfolio_returns),
            'annualized_volatility': self._annualized_volatility(portfolio_returns),
            'sharpe_ratio': self._sharpe_ratio(portfolio_returns),
            'max_drawdown': self._max_drawdown(cumulative),
            'calmar_ratio': self._calmar_ratio(portfolio_returns, cumulative),
            'sortino_ratio': self._sortino_ratio(portfolio_returns),
            'var_95': self._var_95(portfolio_returns),
            'cvar_95': self._cvar_95(portfolio_returns),
            'win_rate': self._win_rate(portfolio_returns),
            'daily_returns_mean': portfolio_returns.mean(),
            'daily_returns_std': portfolio_returns.std(),
            'start_date': portfolio_returns.index[0].strftime('%Y-%m-%d'),
            'end_date': portfolio_returns.index[-1].strftime('%Y-%m-%d'),
            'trading_days': len(portfolio_returns),
        }
        
        return self.results
    
    def _calculate_portfolio_returns(self, start_date=None, end_date=None):
        """计算组合日收益率"""
        asset_returns = {}
        for key, prices in self.prices.items():
            if prices is not None and len(prices) > 1:
                returns = prices.pct_change().dropna()
                if start_date:
                    returns = returns[returns.index >= start_date]
                if end_date:
                    returns = returns[returns.index <= end_date]
                asset_returns[key] = returns
        
        if not asset_returns:
            return None
            
        df_returns = pd.DataFrame(asset_returns)
        df_returns = df_returns.dropna()
        
        if len(df_returns) == 0:
            return None
        
        class_returns = {}
        for asset_class in ['bond', 'money', 'qdii']:
            class_cols = [k for k in df_returns.columns if k.startswith(f"{asset_class}_")]
            if class_cols:
                class_returns[asset_class] = df_returns[class_cols].mean(axis=1)
        
        if not class_returns:
            return None
            
        class_df = pd.DataFrame(class_returns)
        
        weights = pd.Series(self.allocation)
        weights = weights.reindex(class_df.columns).fillna(0)
        weights = weights / weights.sum()
        
        portfolio_returns = (class_df * weights).sum(axis=1)
        
        return portfolio_returns
    
    def _annualized_return(self, returns):
        return (1 + returns.mean()) ** 252 - 1
    
    def _annualized_volatility(self, returns):
        return returns.std() * np.sqrt(252)
    
    def _sharpe_ratio(self, returns, risk_free_rate=0.02):
        excess_return = self._annualized_return(returns) - risk_free_rate
        vol = self._annualized_volatility(returns)
        return excess_return / vol if vol > 0 else 0
    
    def _max_drawdown(self, cumulative):
        peak = cumulative.expanding().max()
        drawdown = (cumulative - peak) / peak
        return drawdown.min()
    
    def _calmar_ratio(self, returns, cumulative):
        ann_return = self._annualized_return(returns)
        mdd = abs(self._max_drawdown(cumulative))
        return ann_return / mdd if mdd > 0 else 0
    
    def _sortino_ratio(self, returns, risk_free_rate=0.02):
        excess_return = self._annualized_return(returns) - risk_free_rate
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252)
        return excess_return / downside_std if downside_std > 0 else 0
    
    def _var_95(self, returns):
        return np.percentile(returns, 5)
    
    def _cvar_95(self, returns):
        var = self._var_95(returns)
        return returns[returns <= var].mean()
    
    def _win_rate(self, returns):
        return (returns > 0).mean()

# ============ 5. 定投回测 ============
class SIPBacktest:
    def __init__(self, prices, monthly_amount=50000):
        self.prices = prices
        self.monthly_amount = monthly_amount
        
    def run_sip(self, asset_key, years=3):
        if asset_key not in self.prices or self.prices[asset_key] is None:
            return None
            
        prices = self.prices[asset_key]
        end_date = prices.index[-1]
        start_date = end_date - pd.DateOffset(years=years)
        prices = prices[prices.index >= start_date]
        
        if len(prices) == 0:
            return None
        
        monthly_dates = prices.resample('ME').last().index
        
        total_invested = 0
        total_shares = 0
        records = []
        
        for date in monthly_dates:
            available_prices = prices[prices.index <= date]
            if len(available_prices) == 0:
                continue
            price = available_prices.iloc[-1]
            
            shares = self.monthly_amount / price
            total_shares += shares
            total_invested += self.monthly_amount
            
            current_value = total_shares * price
            records.append({
                'date': date.strftime('%Y-%m-%d'),
                'price': float(price),
                'shares': float(shares),
                'total_shares': float(total_shares),
                'total_invested': float(total_invested),
                'current_value': float(current_value),
                'return': float((current_value - total_invested) / total_invested)
            })
        
        if not records:
            return None
            
        df = pd.DataFrame(records)
        final_value = df['current_value'].iloc[-1]
        final_return = (final_value - total_invested) / total_invested
        
        return {
            'asset': asset_key,
            'total_invested': float(total_invested),
            'final_value': round(float(final_value), 2),
            'total_return': round(float(final_return) * 100, 2),
            'annualized_return': round(float((1 + final_return) ** (1/years) - 1) * 100, 2),
            'records': records
        }

# ============ 6. 蒙特卡洛模拟 ============
class MonteCarloSimulation:
    def __init__(self, allocation, initial_value=707301, years=10, n_simulations=1000):
        self.allocation = allocation
        self.initial_value = initial_value
        self.years = years
        self.n_simulations = n_simulations
        
    def run_simulation(self):
        """运行蒙特卡洛模拟"""
        n_days = self.years * 252
        
        # 计算组合预期收益和波动率
        portfolio_return = 0
        portfolio_var = 0
        
        for asset_class, weight in self.allocation.items():
            if asset_class == 'bond':
                avg_return = (ASSET_PARAMS['bond_china_bond']['annual_return'] * 0.6 +
                             ASSET_PARAMS['bond_usd_bond']['annual_return'] * 0.1 +
                             ASSET_PARAMS['bond_money_market']['annual_return'] * 0.3)
                avg_vol = (ASSET_PARAMS['bond_china_bond']['annual_volatility'] * 0.6 +
                          ASSET_PARAMS['bond_usd_bond']['annual_volatility'] * 0.1 +
                          ASSET_PARAMS['bond_money_market']['annual_volatility'] * 0.3)
            elif asset_class == 'money':
                avg_return = ASSET_PARAMS['money_money_market']['annual_return']
                avg_vol = ASSET_PARAMS['money_money_market']['annual_volatility']
            elif asset_class == 'qdii':
                avg_return = (ASSET_PARAMS['qdii_nasdaq100']['annual_return'] * 0.45 +
                             ASSET_PARAMS['qdii_global_tech']['annual_return'] * 0.43 +
                             ASSET_PARAMS['qdii_sp500']['annual_return'] * 0.10 +
                             ASSET_PARAMS['qdii_emerging']['annual_return'] * 0.02)
                avg_vol = (ASSET_PARAMS['qdii_nasdaq100']['annual_volatility'] * 0.45 +
                          ASSET_PARAMS['qdii_global_tech']['annual_volatility'] * 0.43 +
                          ASSET_PARAMS['qdii_sp500']['annual_volatility'] * 0.10 +
                          ASSET_PARAMS['qdii_emerging']['annual_volatility'] * 0.02)
            else:
                continue
                
            portfolio_return += weight * avg_return
            portfolio_var += (weight * avg_vol) ** 2
        
        portfolio_vol = np.sqrt(portfolio_var)
        
        daily_return = portfolio_return / 252
        daily_vol = portfolio_vol / np.sqrt(252)
        
        # 运行模拟
        final_values = []
        all_paths = []
        
        for i in range(self.n_simulations):
            returns = np.random.normal(daily_return, daily_vol, n_days)
            cumulative = np.cumprod(1 + returns)
            path = self.initial_value * cumulative
            final_values.append(path[-1])
            if i < 100:  # 只保存前100条路径用于绘图
                all_paths.append(path)
        
        final_values = np.array(final_values)
        
        return {
            'mean_final': np.mean(final_values),
            'median_final': np.median(final_values),
            'std_final': np.std(final_values),
            'percentile_5': np.percentile(final_values, 5),
            'percentile_25': np.percentile(final_values, 25),
            'percentile_75': np.percentile(final_values, 75),
            'percentile_95': np.percentile(final_values, 95),
            'prob_profit': np.mean(final_values > self.initial_value),
            'prob_double': np.mean(final_values > self.initial_value * 2),
            'paths': all_paths,
            'expected_annual_return': portfolio_return,
            'expected_volatility': portfolio_vol
        }

# ============ 7. 主程序 ============
def main():
    print("=" * 60)
    print("支付宝资产配置回测分析")
    print("=" * 60)
    
    end_date = datetime(2026, 6, 23)
    start_date_1y = end_date - timedelta(days=365)
    start_date_3y = end_date - timedelta(days=365*3)
    start_date_5y = end_date - timedelta(days=365*5)
    
    # 生成模拟数据
    print("\n【1】生成模拟市场数据（基于真实统计参数）...")
    prices_5y = generate_simulated_prices(start_date_5y, end_date, seed=42)
    prices_3y = generate_simulated_prices(start_date_3y, end_date, seed=43)
    prices_1y = generate_simulated_prices(start_date_1y, end_date, seed=44)
    
    print(f"  5年数据: {len(list(prices_5y.values())[0])} 个交易日")
    print(f"  3年数据: {len(list(prices_3y.values())[0])} 个交易日")
    print(f"  1年数据: {len(list(prices_1y.values())[0])} 个交易日")
    
    # 运行各场景回测
    print("\n【2】运行配置回测...")
    backtest_results = {}
    
    for scenario_key, scenario in PROPOSED_SCENARIOS.items():
        print(f"\n  场景: {scenario['name']}")
        
        result_5y = BacktestEngine(prices_5y, scenario['allocation']).run_backtest()
        result_3y = BacktestEngine(prices_3y, scenario['allocation']).run_backtest()
        result_1y = BacktestEngine(prices_1y, scenario['allocation']).run_backtest()
        
        backtest_results[scenario_key] = {
            'info': scenario,
            '5y': result_5y,
            '3y': result_3y,
            '1y': result_1y
        }
        
        if result_1y:
            print(f"    1年收益: {result_1y['total_return']*100:.2f}%, 夏普: {result_1y['sharpe_ratio']:.2f}, 最大回撤: {result_1y['max_drawdown']*100:.2f}%")
        if result_3y:
            print(f"    3年收益: {result_3y['total_return']*100:.2f}%, 夏普: {result_3y['sharpe_ratio']:.2f}, 最大回撤: {result_3y['max_drawdown']*100:.2f}%")
    
    # 定投回测
    print("\n【3】运行定投回测...")
    sip_results = {}
    sip = SIPBacktest(prices_5y, monthly_amount=50000)
    
    for asset_key in ['qdii_nasdaq100', 'qdii_global_tech', 'bond_china_bond']:
        result = sip.run_sip(asset_key, years=3)
        if result:
            sip_results[asset_key] = result
            print(f"  {asset_key}: 投入{result['total_invested']:,.0f}, 终值{result['final_value']:,.0f}, 收益{result['total_return']:.2f}%")
    
    # 蒙特卡洛模拟
    print("\n【4】运行蒙特卡洛模拟（10年期）...")
    mc_results = {}
    for scenario_key, scenario in PROPOSED_SCENARIOS.items():
        mc = MonteCarloSimulation(scenario['allocation'], initial_value=707301, years=10, n_simulations=1000)
        mc_result = mc.run_simulation()
        mc_results[scenario_key] = mc_result
        print(f"  {scenario['name']}: 预期终值 {mc_result['mean_final']:,.0f} (中位数 {mc_result['median_final']:,.0f}), 盈利概率 {mc_result['prob_profit']*100:.1f}%")
    
    # 生成图表
    print("\n【5】生成图表...")
    generate_charts(backtest_results, prices_5y, prices_1y, mc_results)
    
    # 生成报告数据
    print("\n【6】生成报告数据...")
    report_data = generate_report_data(backtest_results, sip_results, mc_results)
    
    with open('/data/user/work/backtest/report_data.json', 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    print("\n✓ 回测完成！")
    return backtest_results, report_data

def generate_charts(backtest_results, prices_5y, prices_1y, mc_results):
    """生成回测图表"""
    
    # 图1: 各场景累计收益对比
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1年累计收益
    ax = axes[0, 0]
    colors = {'current': '#9E9E9E', 'conservative': '#2196F3', 'balanced': '#4CAF50', 
              'growth': '#FF9800', 'aggressive': '#F44336'}
    for scenario_key, result in backtest_results.items():
        if result['1y'] and 'cumulative' in result['1y']:
            cum = result['1y']['cumulative']
            ax.plot(cum.index, (cum - 1) * 100, label=result['info']['name'], 
                   linewidth=2, color=colors.get(scenario_key, 'black'))
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax.set_title('1-Year Cumulative Return Comparison (%)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Date')
    ax.set_ylabel('Return (%)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # 3年累计收益
    ax = axes[0, 1]
    for scenario_key, result in backtest_results.items():
        if result['3y'] and 'cumulative' in result['3y']:
            cum = result['3y']['cumulative']
            ax.plot(cum.index, (cum - 1) * 100, label=result['info']['name'], 
                   linewidth=2, color=colors.get(scenario_key, 'black'))
    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax.set_title('3-Year Cumulative Return Comparison (%)', fontsize=14, fontweight='bold')
    ax.set_xlabel('Date')
    ax.set_ylabel('Return (%)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # 风险收益散点图
    ax = axes[1, 0]
    for scenario_key, result in backtest_results.items():
        if result['3y']:
            ret = result['3y']['annualized_return'] * 100
            vol = result['3y']['annualized_volatility'] * 100
            ax.scatter(vol, ret, s=300, c=colors.get(scenario_key, 'black'), 
                      label=result['info']['name'], alpha=0.7, edgecolors='black', linewidth=2)
            ax.annotate(result['info']['name'], (vol, ret), 
                       xytext=(8, 5), textcoords='offset points', fontsize=10, fontweight='bold')
    ax.set_xlabel('Annualized Volatility (%)', fontsize=12)
    ax.set_ylabel('Annualized Return (%)', fontsize=12)
    ax.set_title('Risk-Return Profile (3-Year)', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    # 最大回撤对比
    ax = axes[1, 1]
    scenarios = []
    mdd_1y = []
    mdd_3y = []
    for scenario_key, result in backtest_results.items():
        if result['1y'] and result['3y']:
            scenarios.append(result['info']['name'])
            mdd_1y.append(abs(result['1y']['max_drawdown']))
            mdd_3y.append(abs(result['3y']['max_drawdown']))
    
    x = np.arange(len(scenarios))
    width = 0.35
    bars1 = ax.bar(x - width/2, mdd_1y, width, label='1-Year', alpha=0.8, color='#42A5F5')
    bars2 = ax.bar(x + width/2, mdd_3y, width, label='3-Year', alpha=0.8, color='#EF5350')
    ax.set_ylabel('Max Drawdown', fontsize=12)
    ax.set_title('Maximum Drawdown Comparison', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=15, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    # 添加数值标签
    for bar in bars1:
        height = bar.get_height()
        ax.annotate(f'{height:.1%}',
                   xy=(bar.get_x() + bar.get_width() / 2, height),
                   xytext=(0, 3), textcoords="offset points",
                   ha='center', va='bottom', fontsize=8)
    for bar in bars2:
        height = bar.get_height()
        ax.annotate(f'{height:.1%}',
                   xy=(bar.get_x() + bar.get_width() / 2, height),
                   xytext=(0, 3), textcoords="offset points",
                   ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    plt.savefig('/data/user/work/backtest/charts_1.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 图2: 资产配置 + 蒙特卡洛 + 夏普对比
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    # 当前配置
    ax = axes[0]
    current_alloc = [72.4, 26.2, 1.4]
    labels = ['Bond\n72.4%', 'Money Market\n26.2%', 'QDII\n1.4%']
    colors_pie = ['#4CAF50', '#2196F3', '#FF9800']
    ax.pie(current_alloc, labels=labels, colors=colors_pie, autopct='', startangle=90,
           explode=(0.02, 0.02, 0.02))
    ax.set_title('Current Allocation', fontsize=14, fontweight='bold')
    
    # 建议配置
    ax = axes[1]
    proposed_alloc = [50, 20, 30]
    labels = ['Bond\n50%', 'Money Market\n20%', 'QDII\n30%']
    ax.pie(proposed_alloc, labels=labels, colors=colors_pie, autopct='', startangle=90,
           explode=(0.02, 0.02, 0.02))
    ax.set_title('Recommended (Balanced)', fontsize=14, fontweight='bold')
    
    # 蒙特卡洛模拟结果
    ax = axes[2]
    scenario_names = []
    mean_values = []
    p5_values = []
    p95_values = []
    for scenario_key, result in mc_results.items():
        scenario_names.append(PROPOSED_SCENARIOS[scenario_key]['name'])
        mean_values.append(result['mean_final'] / 10000)
        p5_values.append(result['percentile_5'] / 10000)
        p95_values.append(result['percentile_95'] / 10000)
    
    x = np.arange(len(scenario_names))
    ax.bar(x, mean_values, alpha=0.8, color=colors.values(), label='Expected Value')
    ax.errorbar(x, mean_values, 
               yerr=[np.array(mean_values) - np.array(p5_values), 
                     np.array(p95_values) - np.array(mean_values)], 
               fmt='none', color='black', capsize=5, label='5%-95% Range')
    ax.set_ylabel('Final Value (10K CNY)', fontsize=12)
    ax.set_title('10-Year Monte Carlo Simulation', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(scenario_names, rotation=15, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('/data/user/work/backtest/charts_2.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    # 图3: 蒙特卡洛路径图
    fig, ax = plt.subplots(figsize=(14, 8))
    
    for scenario_key in ['current', 'balanced', 'aggressive']:
        if scenario_key in mc_results and mc_results[scenario_key]['paths']:
            paths = mc_results[scenario_key]['paths']
            color = colors.get(scenario_key, 'gray')
            label = PROPOSED_SCENARIOS[scenario_key]['name']
            
            for i, path in enumerate(paths[:50]):
                alpha = 0.1 if i > 0 else 0.5
                ax.plot(path / 10000, color=color, alpha=alpha, linewidth=0.5)
            
            # 画平均线
            if paths:
                mean_path = np.mean(paths, axis=0)
                ax.plot(mean_path / 10000, color=color, linewidth=3, label=f'{label} (Mean)')
    
    ax.axhline(y=70.73, color='gray', linestyle='--', alpha=0.5, label='Initial Value')
    ax.set_xlabel('Trading Days', fontsize=12)
    ax.set_ylabel('Portfolio Value (10K CNY)', fontsize=12)
    ax.set_title('Monte Carlo Simulation Paths (10-Year)', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('/data/user/work/backtest/charts_3.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    print("  ✓ 图表已保存")

def generate_report_data(backtest_results, sip_results, mc_results):
    """生成报告所需的JSON数据"""
    
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'portfolio_summary': {
            'total_asset': TOTAL_ASSET,
            'current_allocation': {
                'bond': {'value': 512111.35, 'ratio': 72.4},
                'money': {'value': 185106.10, 'ratio': 26.2},
                'qdii': {'value': 10083.56, 'ratio': 1.4}
            }
        },
        'backtest_scenarios': {},
        'sip_analysis': {},
        'monte_carlo': {},
        'recommendations': []
    }
    
    # 回测结果
    for scenario_key, result in backtest_results.items():
        scenario_data = {
            'name': result['info']['name'],
            'description': result['info']['desc'],
            'allocation': result['info']['allocation']
        }
        
        for period in ['1y', '3y', '5y']:
            if result[period]:
                scenario_data[f'{period}_metrics'] = {
                    'total_return': round(result[period]['total_return'] * 100, 2),
                    'annualized_return': round(result[period]['annualized_return'] * 100, 2),
                    'annualized_volatility': round(result[period]['annualized_volatility'] * 100, 2),
                    'sharpe_ratio': round(result[period]['sharpe_ratio'], 3),
                    'max_drawdown': round(result[period]['max_drawdown'] * 100, 2),
                    'calmar_ratio': round(result[period]['calmar_ratio'], 3),
                    'sortino_ratio': round(result[period]['sortino_ratio'], 3),
                    'win_rate': round(result[period]['win_rate'] * 100, 2),
                    'var_95': round(result[period]['var_95'] * 100, 3),
                    'trading_days': result[period]['trading_days']
                }
        
        report['backtest_scenarios'][scenario_key] = scenario_data
    
    # 定投结果
    for asset_key, result in sip_results.items():
        report['sip_analysis'][asset_key] = result
    
    # 蒙特卡洛结果
    for scenario_key, result in mc_results.items():
        report['monte_carlo'][scenario_key] = {
            'name': PROPOSED_SCENARIOS[scenario_key]['name'],
            'mean_final': round(result['mean_final'], 2),
            'median_final': round(result['median_final'], 2),
            'percentile_5': round(result['percentile_5'], 2),
            'percentile_25': round(result['percentile_25'], 2),
            'percentile_75': round(result['percentile_75'], 2),
            'percentile_95': round(result['percentile_95'], 2),
            'prob_profit': round(result['prob_profit'] * 100, 1),
            'prob_double': round(result['prob_double'] * 100, 1),
            'expected_annual_return': round(result['expected_annual_return'] * 100, 2),
            'expected_volatility': round(result['expected_volatility'] * 100, 2)
        }
    
    # 生成建议
    report['recommendations'] = generate_recommendations(backtest_results, mc_results)
    
    return report

def generate_recommendations(backtest_results, mc_results):
    """基于回测结果生成投资建议"""
    recommendations = []
    
    # 找出最佳夏普比率的配置
    best_sharpe = None
    best_sharpe_value = -999
    for key, result in backtest_results.items():
        if result['3y'] and result['3y']['sharpe_ratio'] > best_sharpe_value:
            best_sharpe_value = result['3y']['sharpe_ratio']
            best_sharpe = key
    
    # 找出最佳收益的配置
    best_return = None
    best_return_value = -999
    for key, result in backtest_results.items():
        if result['3y'] and result['3y']['annualized_return'] > best_return_value:
            best_return_value = result['3y']['annualized_return']
            best_return = key
    
    # 找出最小回撤的配置
    min_dd = None
    min_dd_value = 999
    for key, result in backtest_results.items():
        if result['3y'] and abs(result['3y']['max_drawdown']) < min_dd_value:
            min_dd_value = abs(result['3y']['max_drawdown'])
            min_dd = key
    
    # 蒙特卡洛最佳
    best_mc = None
    best_mc_value = -999
    for key, result in mc_results.items():
        if result['prob_profit'] > best_mc_value:
            best_mc_value = result['prob_profit']
            best_mc = key
    
    recommendations.append({
        'type': 'sharpe',
        'title': '最佳风险调整后收益配置',
        'scenario': backtest_results[best_sharpe]['info']['name'] if best_sharpe else 'N/A',
        'value': round(best_sharpe_value, 3) if best_sharpe else 0,
        'description': f"夏普比率最高({best_sharpe_value:.3f})，单位风险收益最优"
    })
    
    recommendations.append({
        'type': 'return',
        'title': '最高收益配置',
        'scenario': backtest_results[best_return]['info']['name'] if best_return else 'N/A',
        'value': round(best_return_value * 100, 2) if best_return else 0,
        'description': f"年化收益最高({best_return_value*100:.2f}%)，适合风险承受能力强的投资者"
    })
    
    recommendations.append({
        'type': 'drawdown',
        'title': '最稳健配置',
        'scenario': backtest_results[min_dd]['info']['name'] if min_dd else 'N/A',
        'value': round(min_dd_value * 100, 2) if min_dd else 0,
        'description': f"最大回撤最小({min_dd_value*100:.2f}%)，适合保守型投资者"
    })
    
    recommendations.append({
        'type': 'montecarlo',
        'title': '最高盈利概率配置（10年）',
        'scenario': PROPOSED_SCENARIOS[best_mc]['name'] if best_mc else 'N/A',
        'value': round(best_mc_value * 100, 1) if best_mc else 0,
        'description': f"10年盈利概率最高({best_mc_value*100:.1f}%)"
    })
    
    return recommendations

if __name__ == '__main__':
    main()
