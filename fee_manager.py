#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一费率管理器（整合 alipay-quant-system FeeManager + fund-trend-system fee_model）
- C类基金费率分档: <7天 1.5% (BLOCK) / 7-29天 0.5% (WARN) / >=30天 0%
- 申购费(支付宝C类通常0) + 赎回费阶梯
- 净收益计算（扣费后）
- 交易值不值过滤器（预期收益 vs 费用门槛）
- 费率解锁日历（持仓解锁日期排序）
"""
from datetime import datetime, date, timedelta

# ===================== 默认配置 =====================
DEFAULT_CONFIG = {
    "default_lock_days": 7,       # C类最短持有期（7天内赎回收惩罚费）
    "buy_fee_rate": 0.0,          # C类申购费（支付宝折扣后通常为0）
    "fee_schedule": [
        {"max_days": 6,   "rate": 0.015,  "label": "1.5%", "severity": "BLOCK",
         "rule": "C类7天内赎回收1.5%惩罚费，严禁操作"},
        {"max_days": 29,  "rate": 0.005,  "label": "0.5%", "severity": "WARN",
         "rule": "持有不足30天，赎回费0.5%，尽量等到30天"},
        {"max_days": 9999, "rate": 0.0,   "label": "0%",   "severity": "OK",
         "rule": "自由操作，无赎回费"},
    ],
    # 交易值不值门槛: 持有天数区间 -> 最低预期收益%
    "worthwhile_thresholds": [
        ((7, 30),   3.0),
        ((30, 365), 2.0),
        ((365, 730), 1.5),
    ],
    "custom_lock_days": {},       # 按基金代码自定义锁定期，如 {"008888": 7}
}


class FeeManager:
    """C类基金统一费率管理器"""

    def __init__(self, config=None):
        cfg = {**DEFAULT_CONFIG, **(config or {})}
        self.default_lock_days = cfg["default_lock_days"]
        self.buy_fee_rate = cfg["buy_fee_rate"]
        self.fee_schedule = cfg["fee_schedule"]
        self.worthwhile_thresholds = cfg["worthwhile_thresholds"]
        self.custom_lock_days = cfg["custom_lock_days"]

    # ---------- 基础查询 ----------
    def get_lock_days(self, fund_code=""):
        return self.custom_lock_days.get(fund_code, self.default_lock_days)

    def get_fee_tier(self, days_held, fund_code=""):
        """返回持有 days_held 天对应的费率等级（含解锁日历信息）"""
        lock_days = self.get_lock_days(fund_code)
        for tier in self.fee_schedule:
            effective_max = tier["max_days"]
            if tier["severity"] == "BLOCK":
                effective_max = lock_days - 1
            if days_held <= effective_max:
                remaining = max(0, lock_days - days_held)
                return {
                    "days_held": days_held,
                    "fee_rate": tier["rate"],
                    "fee_label": tier["label"],
                    "severity": tier["severity"],
                    "rule": tier.get("rule", ""),
                    "lock_days": lock_days,
                    "remaining_days": remaining,
                    "unlock_date": (date.today() + timedelta(days=remaining)).isoformat(),
                }
        tier = self.fee_schedule[-1]
        return {
            "days_held": days_held, "fee_rate": 0, "fee_label": "0%",
            "severity": "OK", "rule": tier["rule"], "lock_days": lock_days,
            "remaining_days": 0, "unlock_date": date.today().isoformat(),
        }

    def can_redeem(self, days_held, fund_code=""):
        return self.get_fee_tier(days_held, fund_code)["severity"] != "BLOCK"

    def days_held(self, entry_date_str):
        try:
            entry = datetime.strptime(str(entry_date_str)[:10], "%Y-%m-%d").date()
            return max(0, (date.today() - entry).days)
        except (ValueError, TypeError):
            return 0

    # ---------- 费用计算 ----------
    def calc_trade_cost(self, amount, days_held, fund_code=""):
        """一次申赎的费用: (buy_fee, sell_fee, total_fee)"""
        tier = self.get_fee_tier(days_held, fund_code)
        buy_fee = amount * self.buy_fee_rate
        sell_fee = amount * tier["fee_rate"]
        return buy_fee, sell_fee, buy_fee + sell_fee

    def calc_net_return(self, gross_return_pct, days_held, fund_code=""):
        """毛收益% 扣除赎回费后的净收益%"""
        tier = self.get_fee_tier(days_held, fund_code)
        return gross_return_pct - tier["fee_rate"] * 100

    # ---------- 交易过滤器 ----------
    def is_trade_worthwhile(self, expected_return_pct, days_held, fund_code=""):
        """判断一笔交易扣费后是否值得执行。返回 (ok, reason)"""
        lock_days = self.get_lock_days(fund_code)
        if days_held < lock_days:
            tier = self.get_fee_tier(days_held, fund_code)
            return False, f"持有{days_held}天<{lock_days}天锁定期，赎回费{tier['fee_label']}太高"
        for (lo, hi), threshold in self.worthwhile_thresholds:
            if lo <= days_held < hi:
                if expected_return_pct < threshold:
                    return False, f"预期收益{expected_return_pct:.1f}% < 费用门槛{threshold}%"
                break
        return True, "通过"

    # ---------- 解锁日历 ----------
    def get_fee_calendar(self, holdings):
        """ holdings: [{code,name,entry_date,...}] -> 未解锁/未免费持仓按解锁日排序 """
        calendar = []
        for h in holdings:
            entry = h.get("entry_date", "")
            code = h.get("code", "")
            if not entry:
                continue
            days = self.days_held(entry)
            tier = self.get_fee_tier(days, code)
            if tier["severity"] != "OK":
                calendar.append({
                    "fund_code": code,
                    "fund_name": h.get("name", ""),
                    "entry_date": entry,
                    "days_held": days,
                    "fee_label": tier["fee_label"],
                    "remaining_days": tier["remaining_days"],
                    "unlock_date": tier["unlock_date"],
                })
        return sorted(calendar, key=lambda x: x["remaining_days"])


if __name__ == "__main__":
    fm = FeeManager()
    print("=== C类费率分档 ===")
    for d in [3, 15, 60]:
        t = fm.get_fee_tier(d)
        print(f"持{d}天: {t['fee_label']} ({t['severity']}) 剩余解锁{t['remaining_days']}天")
    print("\n=== 净收益 ===")
    print(f"毛收益5%,持15天 → 净{fm.calc_net_return(5, 15)}%")
    print("\n=== 值不值过滤器 ===")
    for d, r in [(5, 5), (20, 2.5), (60, 1.5), (60, 3)]:
        ok, msg = fm.is_trade_worthwhile(r, d)
        print(f"持{d}天 预期{r}%: {'通过' if ok else '拦截'} - {msg}")
    print("\n=== 解锁日历 ===")
    demo = [{"code": "008888", "name": "半导体C", "entry_date": "2026-10-18"},
            {"code": "005844", "name": "东方人工智能C", "entry_date": "2026-09-01"}]
    for c in fm.get_fee_calendar(demo):
        print(c)
