# 纳指定投助手 | NASDAQ DCA Assistant

> 基于实时数据的智能定投建议

## Overview

纳指定投助手是一个基于实时市场数据的 NASDAQ 指数定投（Dollar-Cost Averaging）决策辅助工具。它提供智能化的定投建议，帮助投资者在波动的市场中优化定投策略。

## Features

- 📈 **实时数据** — 获取 NASDAQ 最新市场数据
- 🧮 **智能定投建议** — 基于市场估值给出定投金额建议
- 💼 **投资组合追踪** — 管理和追踪定投组合表现
- 📊 **卖出策略** — 内置多种卖出策略分析 (`sell-strategy.js`)
- 🔄 **自动缓存更新** — GitHub Actions 自动更新市场数据

## Tech Stack

- **Frontend**: Vanilla JavaScript + HTML/CSS (PWA)
- **Data**: Real-time NASDAQ market data
- **CI/CD**: GitHub Actions (`.github/workflows/update-cache.yml`)
- **Deployment**: Static site with auto-updating cache

## Usage

1. Open `index.html` in a browser (or deploy as a static site)
2. The app automatically fetches the latest market data
3. Get DCA recommendations based on current market conditions

## PWA Support

- `manifest.json` — PWA manifest
- `sw.js` — Service worker for offline support
- Icons for installable app experience

## License

See LICENSE file.
