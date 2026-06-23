#!/usr/bin/env python3
"""
支付宝基金趋势交易系统 - 主入口
用法:
  python main.py backtest     # 运行回测
  python main.py daily        # 每日决策运行
  python main.py report       # 查看最新报告
  python main.py update       # 更新净值数据
"""
import sys
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import yaml
from datetime import date

with open(os.path.join(PROJECT_DIR, "config", "config.yaml")) as f:
    config = yaml.safe_load(f)


def cmd_backtest():
    """运行回测"""
    from engine.backtest import BacktestEngine
    
    codes = [f["code"] for f in config["funds"] if f.get("enabled", True)]
    strategies = ["MA60-120", "Turtle-55-20", "Momentum-60"]
    
    engine = BacktestEngine(initial_capital=config["backtest"]["initial_capital"])
    
    print("=" * 60)
    print("Fund Trend Strategy Backtest")
    print(f"Data Range: {config['backtest']['start_date']} ~ {config['backtest']['end_date']}")
    print(f"Initial Capital: {config['backtest']['initial_capital']:,} RMB")
    print(f"Fee Mode: Full (buy + sell)")
    print("=" * 60)
    
    engine.run_all(codes, strategies)
    summary = engine.summary_table()
    
    print("\n" + summary.to_string(index=False))
    
    # Save report
    report_path = os.path.join(PROJECT_DIR, "output", "reports", f"backtest_{date.today()}.csv")
    summary.to_csv(report_path, index=False, encoding="utf-8-sig")
    print(f"\nReport saved: {report_path}")
    
    # 生成可视化
    _generate_charts(engine)


def _generate_charts(engine):
    """生成回测可视化图表"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import numpy as np
    from engine.strategies import get_strategy
    
    # Use English labels (no CJK fonts available in this environment)
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.family"] = "DejaVu Sans"
    
    if not engine.results:
        print("No backtest results, skipping chart generation")
        return
    
    charts_dir = os.path.join(PROJECT_DIR, "output", "charts")
    os.makedirs(charts_dir, exist_ok=True)
    
    # 1. Strategy Returns Comparison Bar Chart
    summary = engine.summary_table()
    fig, ax = plt.subplots(figsize=(12, 6))
    
    labels = [f"{r['基金'][:10]}\n{r['策略']}" for _, r in summary.iterrows()]
    returns = summary["总收益率(%)"].values
    
    colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in returns]
    bars = ax.bar(range(len(labels)), returns, color=colors, edgecolor="white")
    
    for bar, val in zip(bars, returns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{val:.1f}%", ha="center", fontsize=9)
    
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_title("Strategy Returns Comparison", fontsize=14, fontweight="bold")
    ax.set_ylabel("Total Return (%)")
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, "strategy_returns.png"), dpi=150)
    plt.close()
    
    # 2. MA Strategy NAV Charts with Buy/Sell Signals
    n_funds = len(set(k[0] for k in engine.results.keys()))
    fig, axes = plt.subplots(1, n_funds, figsize=(5 * n_funds, 4))
    if n_funds == 1:
        axes = [axes]
    
    codes_seen = []
    colors = plt.cm.Set2(np.linspace(0, 1, 3))
    
    for ax_idx, (key, result) in enumerate(engine.results.items()):
        code, strategy = key
        if code in codes_seen:
            continue
        
        df = result["df"]
        trades = result["trades"]
        
        df_sorted = df.sort_values("nav_date")
        df_sorted["ma60"] = df_sorted["nav"].rolling(60).mean()
        df_sorted["ma120"] = df_sorted["nav"].rolling(120).mean()
        
        ax = axes[len(codes_seen)]
        ax.plot(df_sorted["nav_date"], df_sorted["nav"], label="NAV", color=colors[0], alpha=0.8, linewidth=1)
        ax.plot(df_sorted["nav_date"], df_sorted["ma60"], label="MA60", color=colors[1], linewidth=1)
        ax.plot(df_sorted["nav_date"], df_sorted["ma120"], label="MA120", color=colors[2], linewidth=1)
        
        for t in trades:
            buy_date = t["buy"].date
            sell_date = t["sell"].date
            ax.scatter(buy_date, t["buy"].nav, color="#2ecc71", marker="^", s=60, zorder=5)
            ax.scatter(sell_date, t["sell"].nav, color="#e74c3c", marker="v", s=60, zorder=5)
        
        name = result["name"][:15]
        ax.set_title(f"{name} ({code})", fontsize=10, fontweight="bold")
        ax.legend(fontsize=7, loc="upper left")
        ax.tick_params(axis="x", rotation=30, labelsize=7)
        
        codes_seen.append(code)
    
    plt.suptitle("Fund NAV + MA60/120 + Buy/Sell Signals", fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, "ma_signals.png"), dpi=150, bbox_inches="tight")
    plt.close()
    
    print(f"Charts saved to: {charts_dir}/")


def cmd_daily():
    """每日运行决策引擎"""
    from engine.decision import DecisionEngine
    from notify.notifier import Notifier
    
    engine = DecisionEngine()
    decisions = engine.daily_run()
    report = engine.format_report(decisions)
    
    print(report)
    
    notifier = Notifier(output_dir=os.path.join(PROJECT_DIR, "output", "reports"))
    report_path = notifier.push_daily_report(decisions, report)
    print(f"\nReport saved: {report_path}")


def cmd_report():
    """查看最新报告"""
    from notify.notifier import Notifier
    notifier = Notifier(output_dir=os.path.join(PROJECT_DIR, "output", "reports"))
    report = notifier.get_latest_report()
    if report:
        print(report)
    else:
        print("暂无报告，请先运行 'python main.py daily'")


def cmd_update():
    """更新净值数据"""
    from data.collector import update_all_funds
    funds = [f for f in config["funds"] if f.get("enabled", True)]
    update_all_funds(funds)


if __name__ == "__main__":
    cmds = {
        "backtest": cmd_backtest,
        "daily": cmd_daily,
        "report": cmd_report,
        "update": cmd_update,
        "b": cmd_backtest,
        "d": cmd_daily,
        "r": cmd_report,
        "u": cmd_update,
    }
    
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "backtest"
    
    if cmd in cmds:
        cmds[cmd]()
    else:
        print(f"用法: python main.py [backtest|daily|report|update]")
        print(f"未知命令: {cmd}")
