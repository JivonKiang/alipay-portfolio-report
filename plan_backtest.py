#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
10%回撤约束配置方案回测模型

说明：
- 当前仓库缺少全部支付宝基金的历史净值序列，因此这里使用资产大类的参数化回测。
- 输出用于前端展示：目标金额、5年模拟回测、10年蒙特卡洛、买入节奏。
- 参数采用保守假设，目的是检验“回撤尽量压在10%以内”的配置是否合理，而不是承诺收益。
"""

import json
import os
import numpy as np
import pandas as pd


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")

TOTAL_ASSET = 677301
EMERGENCY_CASH = 30000
INVESTABLE = TOTAL_ASSET - EMERGENCY_CASH


ASSETS = {
    "bond": {"name": "中短债/纯债", "ret": 0.035, "vol": 0.035},
    "broad": {"name": "宽基指数", "ret": 0.090, "vol": 0.180},
    "tech": {"name": "科技成长", "ret": 0.140, "vol": 0.240},
    "gold": {"name": "黄金", "ret": 0.055, "vol": 0.160},
    "cash": {"name": "机动现金", "ret": 0.018, "vol": 0.003},
}

TARGET = {
    "bond": 0.50,
    "broad": 0.14,
    "tech": 0.06,
    "gold": 0.08,
    "cash": 0.22,
}

PLAN_COMPARISON = {
    "收益版": {"bond": 0.35, "broad": 0.25, "tech": 0.15, "gold": 0.08, "cash": 0.17},
    "均衡版": {"bond": 0.45, "broad": 0.17, "tech": 0.08, "gold": 0.08, "cash": 0.22},
    "风控版": TARGET,
}

CORR = pd.DataFrame(
    [
        [1.00, 0.15, 0.10, 0.00, 0.05],
        [0.15, 1.00, 0.70, 0.05, 0.00],
        [0.10, 0.70, 1.00, 0.05, 0.00],
        [0.00, 0.05, 0.05, 1.00, 0.00],
        [0.05, 0.00, 0.00, 0.00, 1.00],
    ],
    index=["bond", "broad", "tech", "gold", "cash"],
    columns=["bond", "broad", "tech", "gold", "cash"],
)


def portfolio_stats(weights):
    w = pd.Series(weights)
    rets = pd.Series({k: ASSETS[k]["ret"] for k in weights})
    vols = pd.Series({k: ASSETS[k]["vol"] for k in weights})
    cov = CORR.reindex(index=weights.keys(), columns=weights.keys()).mul(vols, axis=0).mul(vols, axis=1)
    exp_ret = float(w.dot(rets))
    exp_vol = float(np.sqrt(w.T.dot(cov).dot(w)))
    return exp_ret, exp_vol


def monte_carlo(weights, years=10, n=5000, seed=20260623):
    np.random.seed(seed)
    exp_ret, exp_vol = portfolio_stats(weights)
    days = years * 252
    daily_ret = exp_ret / 252
    daily_vol = exp_vol / np.sqrt(252)

    finals = []
    max_dds = []
    ann_returns = []
    for _ in range(n):
        r = np.random.normal(daily_ret, daily_vol, days)
        curve = INVESTABLE * np.cumprod(1 + r)
        peak = np.maximum.accumulate(curve)
        dd = (curve - peak) / peak
        final = curve[-1]
        finals.append(final)
        max_dds.append(dd.min())
        ann_returns.append((final / INVESTABLE) ** (1 / years) - 1)

    finals = np.array(finals)
    max_dds = np.array(max_dds)
    ann_returns = np.array(ann_returns)
    return {
        "exp_return": round(exp_ret * 100, 2),
        "exp_vol": round(exp_vol * 100, 2),
        "median_final": round(float(np.median(finals)), 0),
        "p10_final": round(float(np.percentile(finals, 10)), 0),
        "p90_final": round(float(np.percentile(finals, 90)), 0),
        "median_ann": round(float(np.median(ann_returns)) * 100, 2),
        "prob_ann_8": round(float(np.mean(ann_returns >= 0.08)) * 100, 1),
        "prob_ann_10": round(float(np.mean(ann_returns >= 0.10)) * 100, 1),
        "prob_dd_within_10": round(float(np.mean(max_dds >= -0.10)) * 100, 1),
        "p90_drawdown": round(float(np.percentile(max_dds, 10)) * 100, 2),
        "median_drawdown": round(float(np.median(max_dds)) * 100, 2),
    }


def simulated_backtest(weights, years=5, seed=42):
    np.random.seed(seed)
    exp_ret, exp_vol = portfolio_stats(weights)
    days = years * 252
    daily_ret = exp_ret / 252
    daily_vol = exp_vol / np.sqrt(252)
    r = np.random.normal(daily_ret, daily_vol, days)
    curve = INVESTABLE * np.cumprod(1 + r)
    peak = np.maximum.accumulate(curve)
    dd = (curve - peak) / peak
    total_return = curve[-1] / INVESTABLE - 1
    ann_return = (curve[-1] / INVESTABLE) ** (1 / years) - 1
    ann_vol = np.std(r) * np.sqrt(252)
    sharpe = (ann_return - 0.02) / ann_vol if ann_vol > 0 else 0
    return {
        "total_return": round(float(total_return) * 100, 2),
        "ann_return": round(float(ann_return) * 100, 2),
        "ann_vol": round(float(ann_vol) * 100, 2),
        "max_drawdown": round(float(dd.min()) * 100, 2),
        "sharpe": round(float(sharpe), 2),
        "final_value": round(float(curve[-1]), 0),
    }


def main():
    target_amounts = {
        "emergency": EMERGENCY_CASH,
        **{k: round(INVESTABLE * v, 0) for k, v in TARGET.items()},
    }

    comparison = {}
    for name, weights in PLAN_COMPARISON.items():
        comparison[name] = {
            "weights": weights,
            "backtest": simulated_backtest(weights),
            "monte_carlo": monte_carlo(weights, n=3000, seed=123),
        }

    plan = {
        "updated": "2026-06-23",
        "title": "10%回撤约束配置方案",
        "total_asset": TOTAL_ASSET,
        "emergency_cash": EMERGENCY_CASH,
        "investable_asset": INVESTABLE,
        "target_weights": TARGET,
        "target_amounts": target_amounts,
        "expected": {
            "base_ann_return": "5%–7%",
            "upside_ann_return": "7%–9%",
            "risk_limit": "优先把最大回撤压在10%以内",
            "note": "不是收益承诺，实际结果受市场、费率、买入节奏和执行纪律影响",
        },
        "comparison": comparison,
        "backtest": simulated_backtest(TARGET),
        "monte_carlo": monte_carlo(TARGET),
        "purchase_plan": [
            {"week": "第1周", "amount": 60000, "items": {"中短债/纯债": 25000, "A500/沪深300": 12000, "中证500/1000": 8000, "纳指/全球科技": 5000, "黄金": 10000}},
            {"week": "第2周", "amount": 60000, "items": {"中短债/纯债": 25000, "A500/沪深300": 10000, "中证500/1000": 8000, "标普500/全球宽基": 7000, "半导体/AI/科创50": 4000, "黄金": 6000}},
            {"week": "第3周", "amount": 50000, "items": {"中短债/纯债": 20000, "宽基指数": 12000, "科技成长": 8000, "黄金": 10000}},
            {"week": "第4周", "amount": 40000, "items": {"中短债/纯债": 15000, "宽基指数": 10000, "科技成长": 6000, "黄金": 9000}},
        ],
        "alipay_rules": [
            "工作日15:00前下单按当天净值，15:00后按下一个交易日净值。",
            "核心仓尽量持有6个月以上，避免7天内赎回费。",
            "长期核心仓优先看A类或低费率联接；半年内可能调整的战术仓优先比较C类。",
            "QDII基金净值更新慢、额度可能限制，不做短线交易。",
            "每季度检查一次，偏离目标5%以上再调仓。",
        ],
    }

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["allocation_plan"] = plan
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
