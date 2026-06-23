---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 26b1781be07ad8aded48426f78a59067_fddaaaa36e5411f1a0095254002afed2
    ReservedCode1: Q42DpSgy9ic4P7g/LrK8KUtL238s5gIcuUXJoEQfj+c+xyuXRawLASkTQdeKAKVufpqK6yB6jpZ78Q9/+jzlkKZgXCplPjsmmJmLtXej9I56fzknBjicWJFnHdz8lGNBH3uU4OJ4ol4juyVyUmg575Me0JvLEkgjTI7ST5yguVoRSsh6e+59DUMcI58=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 26b1781be07ad8aded48426f78a59067_fddaaaa36e5411f1a0095254002afed2
    ReservedCode2: Q42DpSgy9ic4P7g/LrK8KUtL238s5gIcuUXJoEQfj+c+xyuXRawLASkTQdeKAKVufpqK6yB6jpZ78Q9/+jzlkKZgXCplPjsmmJmLtXej9I56fzknBjicWJFnHdz8lGNBH3uU4OJ4ol4juyVyUmg575Me0JvLEkgjTI7ST5yguVoRSsh6e+59DUMcI58=
---

# 支付宝基金趋势交易量化系统

基于真实天天基金数据，纯趋势策略的信号生成 + 费用过滤 + 推送通知系统。

## 快速开始

```bash
cd fund-trend-system
pip install pyyaml pandas numpy matplotlib requests tabulate

# 更新净值数据
python main.py update

# 运行回测
python main.py backtest

# 每日决策信号
python main.py daily
```

## 项目结构

```
fund-trend-system/
├── config/config.yaml           # 基金列表 / 策略参数 / 费用配置
├── data/
│   ├── collector.py             # 天天基金 API 数据采集
│   ├── database.py              # SQLite 建表 / 连接管理
│   └── fund_system.db           # 信号 + 净值 + 持仓数据库
├── engine/
│   ├── strategies/__init__.py   # MA / Turtle / Momentum 策略
│   ├── backtest.py              # 回测引擎（含费用模拟）
│   └── decision.py              # 决策引擎（信号 + 费用过滤）
├── fee/fee_model.py             # 申赎费率阶梯 + 费用过滤器
├── notify/notifier.py           # 通知模块（Markdown + JSON 报告）
├── main.py                      # CLI 入口
└── output/
    ├── charts/                  # 回测可视化图表
    └── reports/                 # 日报 + 回测 CSV
```

## 回测结论

| 结论 | 详情 |
|------|------|
| 最优策略 | **MA60-120** - 交易少、费用低、夏普高 |
| 最优品种 | 创业板 > 中证500 > 沪深300 |
| Turtle 缺陷 | 交易过多(6-7次)，费用吃掉 60%+ 利润 |
| Momentum 不足 | 仅 1 笔交易，样本过小不可靠 |

### 核心数据（100,000 初始资金，含申购赎回费）

| 基金 | MA60-120 总收益 | 年化 | 交易次数 | 夏普 |
|------|---------------|------|---------|------|
| 沪深300 | +27.1% | 10.4% | 2 | 11.19 |
| 中证500 | +36.7% | 13.9% | 3 | 8.13 |
| 创业板 | +78.6% | 27.2% | 2 | 10.99 |

## 费用模型

| 持有天数 | 赎回费率 | 场景 |
|---------|---------|------|
| < 7天 | 1.5% | 禁止操作 |
| 7-30天 | 0.75% | 短线 |
| 30-365天 | 0.5% | 中线 |
| 365-730天 | 0.25% | 长线 |
| > 730天 | 0% | 无赎回费 |

申购费统一 0.15%（支付宝折扣后）。

## 工作流

1. **数据采集**: `python main.py update` 从天天基金拉取净值
2. **每日决策**: `python main.py daily` 生成信号 + 推送到 `output/reports/`
3. **验证回测**: `python main.py backtest` 对比策略表现
4. **手动执行**: 根据信号在支付宝 App 手动交易

## 技术栈

- Python 3.11+ | SQLite | Pandas | Matplotlib
- 天天基金开放 API（无需 key）
- 支付宝标准费率阶梯

## 风险提示

- 历史回测不代表未来表现，实盘收益建议打 7 折
- 行业基金（医疗/消费）不适合纯趋势策略
- 参数过拟合风险：未做样本外验证
- 仅适用于宽基指数 ETF 联接基金
*（内容由AI生成，仅供参考）*
