// ============================================================
// 纳指定投助手 - 投资组合/财产管理模块
// ============================================================
// 依赖：app.js（角色系统 getCurrentProfile, currentProfileId）
// 数据源：cache.json（NDX最新价格）
// 暴露API：window.PortfolioManager
// ============================================================

(function () {
  'use strict';

  // ===== 常量 =====
  var STORAGE_KEY = 'nasdaq_dca_portfolio';
  var CHECKSUM_KEY = 'nasdaq_dca_portfolio_checksum';
  var CACHE_URL = './cache.json';

  // ===== 工具函数 =====
  function computeChecksum(str) {
    var hash = 0;
    for (var i = 0; i < str.length; i++) {
      var char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString(16);
  }

  function formatDateStr(date) {
    var y = date.getFullYear();
    var m = ('0' + (date.getMonth() + 1)).slice(-2);
    var d = ('0' + date.getDate()).slice(-2);
    return y + '-' + m + '-' + d;
  }

  function formatMoney(num) {
    if (typeof num !== 'number' || isNaN(num)) return '0.00';
    return num.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function formatPercent(num) {
    if (typeof num !== 'number' || isNaN(num)) return '0.00%';
    var sign = num >= 0 ? '+' : '';
    return sign + (num * 100).toFixed(2) + '%';
  }

  function generateId() {
    return 'pos_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
  }

  // ===== PortfolioManager 类 =====
  function PortfolioManager() {
    this._positions = [];
    this._sellRecords = [];
    this._latestPrice = 0;
    this._latestPE = 0;
    this._cacheLoaded = false;
    this._init();
  }

  // --- 初始化 ---
  PortfolioManager.prototype._init = function () {
    this._loadFromStorage();
    this._loadCache();
  };

  // --- 数据持久化 ---
  PortfolioManager.prototype._loadFromStorage = function () {
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      var checksum = localStorage.getItem(CHECKSUM_KEY);
      if (saved) {
        if (checksum && computeChecksum(saved) !== checksum) {
          console.warn('[PortfolioManager] 数据校验失败，使用空数据');
          this._positions = [];
          this._sellRecords = [];
        } else {
          var data = JSON.parse(saved);
          this._positions = (data.positions || []).filter(this._validatePosition.bind(this));
          this._sellRecords = data.sellRecords || [];
        }
      }
    } catch (e) {
      console.warn('[PortfolioManager] 加载失败:', e);
      this._positions = [];
      this._sellRecords = [];
    }
  };

  PortfolioManager.prototype._saveToStorage = function () {
    try {
      var data = {
        positions: this._positions,
        sellRecords: this._sellRecords,
        updatedAt: new Date().toISOString()
      };
      var json = JSON.stringify(data);
      localStorage.setItem(STORAGE_KEY, json);
      localStorage.setItem(CHECKSUM_KEY, computeChecksum(json));
    } catch (e) {
      console.error('[PortfolioManager] 保存失败:', e);
    }
  };

  // --- 校验持仓数据 ---
  PortfolioManager.prototype._validatePosition = function (pos) {
    return pos &&
      pos.id &&
      pos.fundCode &&
      pos.buyDate &&
      typeof pos.buyPrice === 'number' && pos.buyPrice > 0 &&
      typeof pos.shares === 'number' && pos.shares > 0 &&
      typeof pos.buyAmount === 'number' && pos.buyAmount > 0;
  };

  // --- 加载缓存获取最新价格 ---
  PortfolioManager.prototype._loadCache = function () {
    var self = this;
    // 优先从全局 marketData 获取（app.js 加载后可用）
    if (typeof marketData !== 'undefined' && marketData && marketData.ndx) {
      self._latestPrice = marketData.ndx.price || 0;
      self._latestPE = marketData.pe || 0;
      self._cacheLoaded = true;
      return;
    }
    // 回退到 fetch cache.json
    try {
      fetch(CACHE_URL)
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (data && data.ndx) {
            self._latestPrice = data.ndx.price || 0;
            self._latestPE = data.pe || 0;
            self._cacheLoaded = true;
          }
        })
        .catch(function (e) {
          console.warn('[PortfolioManager] cache.json 加载失败:', e);
        });
    } catch (e) {
      console.warn('[PortfolioManager] fetch 不可用:', e);
    }
  };

  // --- 更新最新价格（供外部调用） ---
  PortfolioManager.prototype.updateMarketData = function (data) {
    if (data && data.ndx) {
      this._latestPrice = data.ndx.price || 0;
      this._latestPE = data.pe || 0;
      this._cacheLoaded = true;
    }
  };

  // --- 获取当前角色 ---
  PortfolioManager.prototype._getCurrentProfile = function () {
    if (typeof getCurrentProfile === 'function') {
      return getCurrentProfile();
    }
    return { id: 'default', name: '默认账户' };
  };

  // ===== 持仓录入 =====
  PortfolioManager.prototype.addPosition = function (opts) {
    var profile = this._getCurrentProfile();
    var position = {
      id: generateId(),
      profileId: profile.id,
      profileName: profile.name,
      fundCode: opts.fundCode || 'QQQ',
      fundName: opts.fundName || opts.fundCode || 'QQQ',
      buyDate: opts.buyDate || formatDateStr(new Date()),
      buyPrice: parseFloat(opts.buyPrice) || 0,
      shares: parseFloat(opts.shares) || 0,
      buyAmount: parseFloat(opts.buyAmount) || 0,
      createdAt: new Date().toISOString()
    };

    // 自动计算金额或份额
    if (position.buyAmount > 0 && position.shares <= 0 && position.buyPrice > 0) {
      position.shares = position.buyAmount / position.buyPrice;
    } else if (position.shares > 0 && position.buyAmount <= 0 && position.buyPrice > 0) {
      position.buyAmount = position.shares * position.buyPrice;
    }

    if (position.buyPrice <= 0 || position.shares <= 0) {
      console.error('[PortfolioManager] 买入价格和份额必须大于0');
      return null;
    }

    this._positions.push(position);
    this._saveToStorage();
    return position;
  };

  // --- 删除持仓 ---
  PortfolioManager.prototype.removePosition = function (id) {
    this._positions = this._positions.filter(function (p) { return p.id !== id; });
    this._saveToStorage();
  };

  // --- 编辑持仓 ---
  PortfolioManager.prototype.updatePosition = function (id, updates) {
    var pos = this._findPosition(id);
    if (!pos) return null;

    if (updates.fundCode) pos.fundCode = updates.fundCode;
    if (updates.fundName) pos.fundName = updates.fundName;
    if (updates.buyDate) pos.buyDate = updates.buyDate;
    if (typeof updates.buyPrice === 'number') pos.buyPrice = updates.buyPrice;
    if (typeof updates.shares === 'number') pos.shares = updates.shares;
    if (typeof updates.buyAmount === 'number') pos.buyAmount = updates.buyAmount;

    // 重新计算
    if (pos.buyPrice > 0 && pos.shares > 0) {
      pos.buyAmount = pos.shares * pos.buyPrice;
    }

    this._saveToStorage();
    return pos;
  };

  // --- 查找持仓 ---
  PortfolioManager.prototype._findPosition = function (id) {
    for (var i = 0; i < this._positions.length; i++) {
      if (this._positions[i].id === id) return this._positions[i];
    }
    return null;
  };

  // ===== 市值计算 =====
  PortfolioManager.prototype.calculateMarketValue = function (position) {
    if (!position || !this._cacheLoaded || this._latestPrice <= 0) {
      return {
        marketValue: position ? position.buyAmount : 0,
        profit: 0,
        profitRate: 0,
        annualizedRate: 0,
        currentPrice: this._latestPrice || (position ? position.buyPrice : 0)
      };
    }

    var currentPrice = this._latestPrice;
    var marketValue = currentPrice * position.shares;
    var cost = position.buyAmount;
    var profit = marketValue - cost;
    var profitRate = cost > 0 ? profit / cost : 0;

    // 年化收益率
    var buyDate = new Date(position.buyDate);
    var now = new Date();
    var holdDays = (now - buyDate) / (1000 * 60 * 60 * 24);
    var annualizedRate = 0;
    if (holdDays > 0 && profitRate !== 0) {
      annualizedRate = Math.pow(1 + profitRate, 365 / holdDays) - 1;
    }

    return {
      marketValue: marketValue,
      profit: profit,
      profitRate: profitRate,
      annualizedRate: annualizedRate,
      currentPrice: currentPrice
    };
  };

  // ===== 总资产汇总 =====
  PortfolioManager.prototype.getSummary = function () {
    var profile = this._getCurrentProfile();
    var profilePositions = this._positions.filter(function (p) {
      return p.profileId === profile.id;
    });

    var totalCost = 0;
    var totalMarketValue = 0;
    var totalProfit = 0;

    for (var i = 0; i < profilePositions.length; i++) {
      var calc = this.calculateMarketValue(profilePositions[i]);
      totalCost += profilePositions[i].buyAmount;
      totalMarketValue += calc.marketValue;
      totalProfit += calc.profit;
    }

    var totalProfitRate = totalCost > 0 ? totalProfit / totalCost : 0;

    return {
      profileId: profile.id,
      profileName: profile.name,
      positionCount: profilePositions.length,
      totalCost: totalCost,
      totalMarketValue: totalMarketValue,
      totalProfit: totalProfit,
      totalProfitRate: totalProfitRate,
      currentPrice: this._latestPrice,
      currentPE: this._latestPE,
      positions: profilePositions
    };
  };

  // ===== 获取所有持仓 =====
  PortfolioManager.prototype.getPositions = function () {
    var profile = this._getCurrentProfile();
    return this._positions.filter(function (p) {
      return p.profileId === profile.id;
    });
  };

  // ===== 获取卖出记录 =====
  PortfolioManager.prototype.getSellRecords = function () {
    var profile = this._getCurrentProfile();
    return this._sellRecords.filter(function (r) {
      return r.profileId === profile.id;
    });
  };

  // ===== 添加卖出记录（供 SellStrategy 调用） =====
  PortfolioManager.prototype.addSellRecord = function (record) {
    var profile = this._getCurrentProfile();
    var sellRecord = {
      id: 'sell_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6),
      profileId: profile.id,
      profileName: profile.name,
      positionId: record.positionId || null,
      fundCode: record.fundCode || 'QQQ',
      fundName: record.fundName || record.fundCode || 'QQQ',
      sellDate: record.sellDate || formatDateStr(new Date()),
      sellShares: parseFloat(record.sellShares) || 0,
      sellPrice: parseFloat(record.sellPrice) || 0,
      sellAmount: parseFloat(record.sellAmount) || 0,
      sellReason: record.sellReason || '',
      profit: parseFloat(record.profit) || 0,
      profitRate: parseFloat(record.profitRate) || 0,
      createdAt: new Date().toISOString()
    };

    if (sellRecord.sellShares > 0 && sellRecord.sellPrice > 0) {
      sellRecord.sellAmount = sellRecord.sellShares * sellRecord.sellPrice;
    }

    this._sellRecords.push(sellRecord);
    this._saveToStorage();
    return sellRecord;
  };

  // ===== CSV导出 =====
  PortfolioManager.prototype.exportCSV = function () {
    var positions = this.getPositions();
    var sellRecords = this.getSellRecords();
    var lines = [];

    // 持仓表头
    lines.push('=== 持仓记录 ===');
    lines.push('基金代码,基金名称,买入日期,买入价格,买入份额,买入金额,当前价格,当前市值,累计收益,收益率,年化收益率');
    for (var i = 0; i < positions.length; i++) {
      var pos = positions[i];
      var calc = this.calculateMarketValue(pos);
      lines.push([
        pos.fundCode,
        '"' + (pos.fundName || '') + '"',
        pos.buyDate,
        pos.buyPrice.toFixed(4),
        pos.shares.toFixed(4),
        pos.buyAmount.toFixed(2),
        calc.currentPrice.toFixed(4),
        calc.marketValue.toFixed(2),
        calc.profit.toFixed(2),
        (calc.profitRate * 100).toFixed(2) + '%',
        (calc.annualizedRate * 100).toFixed(2) + '%'
      ].join(','));
    }

    // 空行
    lines.push('');

    // 卖出记录
    lines.push('=== 卖出记录 ===');
    lines.push('基金代码,基金名称,卖出日期,卖出份额,卖出价格,卖出金额,卖出原因,收益,收益率');
    for (var j = 0; j < sellRecords.length; j++) {
      var sr = sellRecords[j];
      lines.push([
        sr.fundCode,
        '"' + (sr.fundName || '') + '"',
        sr.sellDate,
        sr.sellShares.toFixed(4),
        sr.sellPrice.toFixed(4),
        sr.sellAmount.toFixed(2),
        '"' + (sr.sellReason || '') + '"',
        sr.profit.toFixed(2),
        (sr.profitRate * 100).toFixed(2) + '%'
      ].join(','));
    }

    // 汇总
    lines.push('');
    lines.push('=== 汇总 ===');
    var summary = this.getSummary();
    lines.push('总持仓数,' + summary.positionCount);
    lines.push('总成本,' + summary.totalCost.toFixed(2));
    lines.push('总市值,' + summary.totalMarketValue.toFixed(2));
    lines.push('总收益,' + summary.totalProfit.toFixed(2));
    lines.push('总收益率,' + (summary.totalProfitRate * 100).toFixed(2) + '%');

    var csvContent = '\uFEFF' + lines.join('\n');
    var blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'portfolio-' + formatDateStr(new Date()) + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // ===== 渲染函数 =====
  PortfolioManager.prototype.renderPortfolio = function () {
    var container = document.getElementById('portfolioContainer');
    if (!container) {
      // 如果没有专用容器，尝试插入到定投记录Tab
      var historyTab = document.getElementById('tab-history');
      if (historyTab) {
        container = document.createElement('div');
        container.id = 'portfolioContainer';
        container.style.marginTop = '16px';
        historyTab.appendChild(container);
      } else {
        console.warn('[PortfolioManager] 找不到渲染容器');
        return;
      }
    }

    var summary = this.getSummary();
    var positions = summary.positions;
    var html = '';

    // --- 总资产概览 ---
    html += '<div class="card" style="border: 1px solid rgba(59,130,246,0.3);">';
    html += '  <div class="card-title"><span class="emoji">📊</span> 投资组合概览</div>';
    html += '  <div class="summary-row">';
    html += '    <div class="summary-card">';
    html += '      <div class="label">总市值</div>';
    html += '      <div class="value blue">$' + formatMoney(summary.totalMarketValue) + '</div>';
    html += '    </div>';
    html += '    <div class="summary-card">';
    html += '      <div class="label">总成本</div>';
    html += '      <div class="value muted">$' + formatMoney(summary.totalCost) + '</div>';
    html += '    </div>';
    html += '    <div class="summary-card">';
    html += '      <div class="label">总收益</div>';
    html += '      <div class="value ' + (summary.totalProfit >= 0 ? 'green' : 'red') + '">';
    html += '        ' + (summary.totalProfit >= 0 ? '+' : '') + '$' + formatMoney(summary.totalProfit);
    html += '      </div>';
    html += '      <div class="sub ' + (summary.totalProfitRate >= 0 ? 'green' : 'red') + '">';
    html += '        ' + formatPercent(summary.totalProfitRate);
    html += '      </div>';
    html += '    </div>';
    html += '  </div>';
    html += '  <div class="data-grid">';
    html += '    <div class="data-item">';
    html += '      <div class="data-label">持仓数量</div>';
    html += '      <div class="data-value small">' + summary.positionCount + ' 笔</div>';
    html += '    </div>';
    html += '    <div class="data-item">';
    html += '      <div class="data-label">当前价格 (NDX)</div>';
    html += '      <div class="data-value small blue">$' + formatMoney(summary.currentPrice) + '</div>';
    html += '    </div>';
    html += '    <div class="data-item">';
    html += '      <div class="data-label">当前PE</div>';
    html += '      <div class="data-value small ' + (summary.currentPE > 40 ? 'red' : summary.currentPE > 30 ? 'yellow' : 'green') + '">';
    html += '        ' + (summary.currentPE > 0 ? summary.currentPE.toFixed(2) : '--');
    html += '      </div>';
    html += '    </div>';
    html += '    <div class="data-item">';
    html += '      <div class="data-label">收益率</div>';
    html += '      <div class="data-value small ' + (summary.totalProfitRate >= 0 ? 'green' : 'red') + '">';
    html += '        ' + formatPercent(summary.totalProfitRate);
    html += '      </div>';
    html += '    </div>';
    html += '  </div>';
    html += '</div>';

    // --- 操作按钮 ---
    html += '<div style="display:flex;gap:8px;margin-bottom:12px;">';
    html += '  <button onclick="PortfolioManager.showAddForm()" style="flex:1;padding:10px;background:var(--accent-blue);color:white;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;">+ 添加持仓</button>';
    html += '  <button onclick="PortfolioManager.exportCSV()" style="flex:1;padding:10px;background:rgba(168,85,247,0.2);color:var(--accent-purple);border:1px solid rgba(168,85,247,0.3);border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;">导出CSV</button>';
    html += '</div>';

    // --- 持仓列表 ---
    if (positions.length === 0) {
      html += '<div class="card" style="text-align:center;padding:30px;">';
      html += '  <div style="font-size:32px;margin-bottom:8px;">📭</div>';
      html += '  <div style="color:var(--text-muted);font-size:13px;">暂无持仓记录</div>';
      html += '  <div style="color:var(--text-muted);font-size:11px;margin-top:4px;">点击"添加持仓"开始记录</div>';
      html += '</div>';
    } else {
      html += '<div class="section-divider">持仓明细</div>';
      for (var i = 0; i < positions.length; i++) {
        var pos = positions[i];
        var calc = this.calculateMarketValue(pos);
        var profitClass = calc.profit >= 0 ? 'green' : 'red';

        html += '<div class="card" style="padding:12px;">';
        html += '  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">';
        html += '    <div>';
        html += '      <div style="font-size:14px;font-weight:700;">' + (pos.fundName || pos.fundCode) + '</div>';
        html += '      <div style="font-size:11px;color:var(--text-muted);">' + pos.fundCode + ' | ' + pos.buyDate + '</div>';
        html += '    </div>';
        html += '    <div style="text-align:right;">';
        html += '      <div class="' + profitClass + '" style="font-size:15px;font-weight:700;">' + formatPercent(calc.profitRate) + '</div>';
        html += '      <div class="' + profitClass + '" style="font-size:11px;">' + (calc.profit >= 0 ? '+' : '-') + '$' + formatMoney(Math.abs(calc.profit)) + '</div>';
        html += '    </div>';
        html += '  </div>';
        html += '  <div class="data-grid">';
        html += '    <div class="data-item">';
        html += '      <div class="data-label">买入价格</div>';
        html += '      <div class="data-value small">$' + pos.buyPrice.toFixed(4) + '</div>';
        html += '    </div>';
        html += '    <div class="data-item">';
        html += '      <div class="data-label">当前价格</div>';
        html += '      <div class="data-value small blue">$' + calc.currentPrice.toFixed(4) + '</div>';
        html += '    </div>';
        html += '    <div class="data-item">';
        html += '      <div class="data-label">持有份额</div>';
        html += '      <div class="data-value small">' + pos.shares.toFixed(4) + '</div>';
        html += '    </div>';
        html += '    <div class="data-item">';
        html += '      <div class="data-label">当前市值</div>';
        html += '      <div class="data-value small blue">$' + formatMoney(calc.marketValue) + '</div>';
        html += '    </div>';
        html += '    <div class="data-item">';
        html += '      <div class="data-label">买入成本</div>';
        html += '      <div class="data-value small muted">$' + formatMoney(pos.buyAmount) + '</div>';
        html += '    </div>';
        html += '    <div class="data-item">';
        html += '      <div class="data-label">年化收益率</div>';
        html += '      <div class="data-value small ' + profitClass + '">' + formatPercent(calc.annualizedRate) + '</div>';
        html += '    </div>';
        html += '  </div>';
        html += '  <div style="display:flex;gap:6px;margin-top:8px;">';
        html += '    <button onclick="PortfolioManager.removePosition(\'' + pos.id + '\');PortfolioManager.renderPortfolio();" style="flex:1;padding:6px;background:rgba(239,68,68,0.1);color:var(--accent-red);border:1px solid rgba(239,68,68,0.2);border-radius:6px;font-size:11px;cursor:pointer;">删除</button>';
        html += '  </div>';
        html += '</div>';
      }
    }

    // --- 卖出记录 ---
    var sellRecords = this.getSellRecords();
    if (sellRecords.length > 0) {
      html += '<div class="section-divider">卖出记录</div>';
      for (var j = 0; j < sellRecords.length; j++) {
        var sr = sellRecords[j];
        var srProfitClass = sr.profit >= 0 ? 'green' : 'red';
        html += '<div class="card" style="padding:10px;">';
        html += '  <div style="display:flex;justify-content:space-between;align-items:center;">';
        html += '    <div>';
        html += '      <div style="font-size:13px;font-weight:600;">卖出 ' + (sr.fundName || sr.fundCode) + '</div>';
        html += '      <div style="font-size:11px;color:var(--text-muted);">' + sr.sellDate + ' | ' + sr.sellReason + '</div>';
        html += '    </div>';
        html += '    <div style="text-align:right;">';
        html += '      <div class="' + srProfitClass + '" style="font-size:13px;font-weight:700;">' + (sr.profit >= 0 ? '+' : '') + '$' + formatMoney(sr.profit) + '</div>';
        html += '      <div class="' + srProfitClass + '" style="font-size:11px;">' + formatPercent(sr.profitRate) + '</div>';
        html += '    </div>';
        html += '  </div>';
        html += '  <div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">';
        html += '    卖出 ' + sr.sellShares.toFixed(4) + ' 份 @ $' + sr.sellPrice.toFixed(4) + ' = $' + formatMoney(sr.sellAmount);
        html += '  </div>';
        html += '</div>';
      }
    }

    container.innerHTML = html;
  };

  // ===== 添加持仓表单 =====
  PortfolioManager.showAddForm = function () {
    var overlay = document.getElementById('portfolioAddOverlay');
    if (overlay) {
      overlay.classList.add('show');
      return;
    }

    // 创建弹窗
    overlay = document.createElement('div');
    overlay.id = 'portfolioAddOverlay';
    overlay.className = 'modal-overlay';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';

    var today = formatDateStr(new Date());
    overlay.innerHTML = '' +
      '<div style="background:var(--bg-card);border-radius:16px;padding:20px;width:90%;max-width:400px;max-height:80vh;overflow-y:auto;">' +
      '  <div style="font-size:16px;font-weight:700;margin-bottom:16px;">添加持仓</div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">基金代码</div>' +
      '    <input id="pf_fundCode" class="setting-input" value="QQQ" placeholder="如 QQQ, NDX">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">基金名称</div>' +
      '    <input id="pf_fundName" class="setting-input" value="Nasdaq-100 ETF" placeholder="基金名称">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">买入日期</div>' +
      '    <input id="pf_buyDate" class="setting-input" type="date" value="' + today + '">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">买入价格 ($)</div>' +
      '    <input id="pf_buyPrice" class="setting-input" type="number" step="0.0001" placeholder="0.0000">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">买入份额</div>' +
      '    <input id="pf_shares" class="setting-input" type="number" step="0.0001" placeholder="0.0000">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">买入金额 ($)（可选，自动计算）</div>' +
      '    <input id="pf_buyAmount" class="setting-input" type="number" step="0.01" placeholder="0.00">' +
      '  </div>' +
      '  <div style="display:flex;gap:8px;margin-top:12px;">' +
      '    <button onclick="PortfolioManager._closeAddForm()" style="flex:1;padding:10px;background:rgba(100,116,139,0.2);color:var(--text-secondary);border:none;border-radius:8px;font-size:14px;cursor:pointer;">取消</button>' +
      '    <button onclick="PortfolioManager._submitAddForm()" style="flex:1;padding:10px;background:var(--accent-blue);color:white;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">确认添加</button>' +
      '  </div>' +
      '</div>';

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) PortfolioManager._closeAddForm();
    });

    document.body.appendChild(overlay);
  };

  PortfolioManager._closeAddForm = function () {
    var overlay = document.getElementById('portfolioAddOverlay');
    if (overlay) {
      overlay.classList.remove('show');
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
  };

  PortfolioManager._submitAddForm = function () {
    var fundCode = document.getElementById('pf_fundCode').value.trim();
    var fundName = document.getElementById('pf_fundName').value.trim();
    var buyDate = document.getElementById('pf_buyDate').value;
    var buyPrice = parseFloat(document.getElementById('pf_buyPrice').value);
    var shares = parseFloat(document.getElementById('pf_shares').value);
    var buyAmount = parseFloat(document.getElementById('pf_buyAmount').value) || 0;

    if (!fundCode || !buyDate || isNaN(buyPrice) || buyPrice <= 0) {
      alert('请填写基金代码、买入日期和有效的买入价格');
      return;
    }
    if (isNaN(shares) || shares <= 0) {
      if (buyAmount <= 0) {
        alert('请填写买入份额或买入金额');
        return;
      }
    }

    var result = window.PortfolioManager.addPosition({
      fundCode: fundCode,
      fundName: fundName || fundCode,
      buyDate: buyDate,
      buyPrice: buyPrice,
      shares: isNaN(shares) ? 0 : shares,
      buyAmount: buyAmount
    });

    if (result) {
      PortfolioManager._closeAddForm();
      PortfolioManager.renderPortfolio();
    }
  };

  // ===== 实例化并暴露到全局 =====
  var instance = new PortfolioManager();
  window.PortfolioManager = instance;

  // 监听 marketData 更新
  var _origRenderAllTabs = window.renderAllTabs;
  if (_origRenderAllTabs) {
    window.renderAllTabs = function (data) {
      instance.updateMarketData(data);
      return _origRenderAllTabs(data);
    };
  }

})();
