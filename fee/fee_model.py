"""
支付宝基金费用模型
精确计算申购费、赎回费（按阶梯）、净收益
"""
from datetime import datetime, date

# 费用阶梯配置
SELL_FEE_TIERS = [
    (7, 0.015),     # < 7天：1.5%
    (30, 0.0075),   # 7-30天：0.75%
    (365, 0.005),   # 30-365天：0.5%
    (730, 0.0025),  # 365-730天：0.25%
]
BUY_FEE_RATE = 0.0015      # 申购费 0.15%（支付宝折扣后）
MIN_HOLD_DAYS = 7          # 最短持有天数（强制过滤）


def get_sell_fee_rate(hold_days):
    """根据持有天数获取赎回费率"""
    for days, rate in SELL_FEE_TIERS:
        if hold_days < days:
            return rate
    return 0  # >= 730天免费


def calc_trade_cost(amount, hold_days):
    """
    计算一次交易的费用
    返回: (buy_fee, sell_fee, total_fee)
    """
    buy_fee = amount * BUY_FEE_RATE
    sell_fee = amount * get_sell_fee_rate(hold_days)
    return buy_fee, sell_fee, buy_fee + sell_fee


def calc_net_return(buy_nav, sell_nav, amount, buy_date, sell_date):
    """
    计算考虑费用后的净收益
    返回: (net_profit, net_return_pct, total_fee)
    """
    if isinstance(buy_date, str):
        buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
    if isinstance(sell_date, str):
        sell_date = datetime.strptime(sell_date, "%Y-%m-%d").date()
    
    hold_days = (sell_date - buy_date).days
    shares = amount * (1 - BUY_FEE_RATE) / buy_nav
    sell_value = shares * sell_nav
    sell_fee = sell_value * get_sell_fee_rate(hold_days)
    buy_fee = amount * BUY_FEE_RATE
    total_fee = buy_fee + sell_fee
    net_profit = sell_value - amount - sell_fee
    net_return_pct = (net_profit / amount) * 100
    return round(net_profit, 2), round(net_return_pct, 2), round(total_fee, 2)


def is_trade_worthwhile(expected_return_pct, hold_days):
    """
    费用过滤器：判断交易是否值得执行
    基于预计持有天数和预期收益率决定
    """
    if hold_days < MIN_HOLD_DAYS:
        return False, "持有不足7天，赎回费1.5%太高"
    
    thresholds = {
        (7, 30): 3.0,      # 需 >3%
        (30, 365): 2.0,    # 需 >2%
        (365, 730): 1.5,   # 需 >1.5%
    }
    
    for (lo, hi), threshold in thresholds.items():
        if lo <= hold_days < hi:
            if expected_return_pct < threshold:
                return False, f"预期收益{expected_return_pct:.1f}% < 费用门槛{threshold}%"
    
    return True, "通过"


if __name__ == "__main__":
    # 测试
    print("=== 费用计算示例 ===")
    amount = 10000
    
    for hold_days in [3, 15, 60, 200, 400, 800]:
        buy_fee, sell_fee, total_fee = calc_trade_cost(amount, hold_days)
        print(f"持{hold_days}天: 申购{buy_fee:.1f} 赎回{sell_fee:.1f} 合计{total_fee:.1f}")
    
    print("\n=== 净收益计算 ===")
    profit, pct, fee = calc_net_return(1.0, 1.25, 10000, "2024-01-01", "2025-01-01")
    print(f"10000元, 净值1.0→1.25, 持365天: 净利{profit}元 ({pct}%), 费{fee}元")
    
    print("\n=== 费用过滤器 ===")
    for hold_days, exp_ret in [(5, 5), (20, 2.5), (60, 1.5), (200, 3)]:
        ok, msg = is_trade_worthwhile(exp_ret, hold_days)
        print(f"持{hold_days}天 预期{exp_ret}%: {'通过' if ok else '拦截'} - {msg}")
