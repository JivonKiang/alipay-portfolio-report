# Jivon 综合资产面板 · Investment Hub

主任全部投资项目的统一面板（七个投资项目归一）。`hub.html` 为投资整合面板本体，
部署于 **https://invest.jivonlab.com**（CNAME 已落，Cloudflare 需加一条 CNAME 记录指向
`jivonkiang.github.io` 后生效）。

## 面板结构（hub.html）

| 区块 | 内容 | 数据源 |
|---|---|---|
| 市场环境横幅 | 熊/牛市判定 · 建议仓位 | `trading_data.json`（每日 11:00/14:30 自动） |
| 资产总览 | 总资产 + 稳健/灵活/进攻三层 | `data.json` → 构建时复制为 `main-data.json` |
| 纳指定投 | NDX 点位 · 回撤 · MA20 信号 | `data.json` |
| 策略实验室 | 七项目归一入口与状态 | 静态（etf-quant-auto / nasdaq-dca / etf-quant / alipay-quant-system / fund-trend-system） |
| 资产配置回测 | 2019-2026 回测摘要 · 定投 IRR | investment-dashboard 归一 |

## 归一台账（2026-11-09）

| 原仓库 | 去向 |
|---|---|
| nasdaq-dca | 已并入本面板（legacy/nasdaq-dca 分支） |
| fund-trend-system | legacy/fund-trend 分支 · README 挂迁移横幅 |
| investment-dashboard | legacy/dashboard 分支 · 回测数据嵌入本面板 |
| etf-quant | 独立运行（Pages 每日更新），面板内挂入口 |
| alipay-quant-system | 独立模块，面板内挂入口 |
| etf-quant-auto | **主战系统**，无人值守每日运行 |
| JivonKiang.github.io | jivonlab.com 首页新增投资面板入口卡 |

## 部署机制

- GitHub Actions `trading-system.yml`（每日 11:00/14:30）跑 `trading_system.py` →
  复制 `hub.html` + `data.json`（为 `main-data.json`）到 `output/` → 发布到 `gh-pages` 分支。
- Pages 从 `gh-pages` 发布，绑定域见 `CNAME`。
- main 分支的 `index.html` 是「操盘手每日修炼」页，由 workflow 自动重写，勿手改后依赖持久化。

## 免责声明

本面板输出的信号与回测结果为模型驱动，仅供研究参考，不构成投资建议。
