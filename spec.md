# 支付宝资产配置报告 - 设计规格书

## 项目概述
基于用户现有 GitHub 仓库（alipay-portfolio-report），全面升级为一个手机端优先、可添加到主屏幕的 PWA 应用，提供美观的资产配置分析、回测报告和投资建议。

## 已学习的现有工作
1. **nasdaq-dca**: 优秀的 PWA 实践（manifest.json、Service Worker、apple-touch-icon、深色主题、sticky header、backdrop-filter）
2. **investment-dashboard**: 暗色主题卡片设计、Chart.js 图表、网格布局
3. **fund-trend-system**: 模块化 Python 回测引擎架构

## 设计方向

### 视觉风格
- **深色主题**（参考 nasdaq-dca 的 slate 色系）
- 手机端全屏体验，无水平滚动
- 底部 Tab 导航（替代顶部 tabs，更适合拇指操作）
- 卡片式信息展示，圆角 12px
- 毛玻璃效果 header

### 页面结构（5个底部 Tab）
1. **概览** - 总资产、昨日收益、资产分布饼图、关键指标
2. **持仓** - 债券明细、QDII 明细、货币基金详情
3. **回测** - 5种配置方案对比、风险收益图、详细指标表
4. **定投** - 定投计划概览、各资产定投回测、收益曲线
5. **建议** - 投资建议卡片、操作清单、风险提示

### 交互设计
- 页面切换使用淡入淡出动画
- 卡片点击可展开详情
- 下拉刷新数据（模拟）
- 数字变化有计数动画
- 图表支持触摸交互

### PWA 配置
- manifest.json（standalone 模式、主题色、图标）
- Service Worker（离线缓存）
- apple-mobile-web-app-capable
- theme-color meta

### 图标设计
- 使用 canvas-design 设计 192x192 和 512x512 图标
- 风格：现代金融感，深色背景 + 渐变 accent

### 回测脚本增强
- 保留现有蒙特卡洛模拟
- 增加多数据源信息收集框架（为后续接入真实数据预留）
- 输出 JSON 数据供前端直接消费

## 技术栈
- 纯 HTML/CSS/JS（GitHub Pages 兼容）
- Chart.js 4.x 图表
- Tailwind CSS（CDN）
- 无框架依赖，单文件应用
