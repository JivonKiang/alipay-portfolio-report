// ============================================================
// 纳指定投助手 - 止盈/卖出策略模块
// ============================================================
// 依赖：app.js（PE估值系统 marketData, peGrade）
// 依赖：portfolio.js（PortfolioManager 持仓数据）
// 暴露API：window.SellStrategy
// ============================================================

(function () {
  'use strict';

  // ===== 常量 =====
  var STORAGE_KEY = 'nasdaq_dca_sell_strategy';
  var CHECKSUM_KEY = 'nasdaq_dca_sell_strategy_checksum';

  // ===== 默认止盈规则 =====
  var DEFAULT_RULES = {
    // PE阈值规则
    peThreshold: {
      enabled: true,
      peLevel1: 35,    // PE>35 提示关注
      peLevel2: 40,    // PE>40 提示减仓50%
      peLevel3: 45,    // PE>45 提示减仓70%
      reducePercent1: 50,
      reducePercent2: 70
    },
    // 收益率规则
    profitThreshold: {
      enabled: true,
      takeProfitRate: 0.30,       // 收益>30% 提示止盈
      strongTakeProfitRate: 0.50,  // 收益>50% 强烈建议止盈
      reducePercent: 100           // 止盈时建议卖出比例
    }
  };

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

  // ===== SellStrategy 类 =====
  function SellStrategy() {
    this._rules = {};
    this._alerts = [];
    this._dismissedAlerts = [];
    this._init();
  }

  // --- 初始化 ---
  SellStrategy.prototype._init = function () {
    this._loadRules();
    this._loadDismissedAlerts();
  };

  // --- 数据持久化：规则 ---
  SellStrategy.prototype._loadRules = function () {
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      var checksum = localStorage.getItem(CHECKSUM_KEY);
      if (saved) {
        if (checksum && computeChecksum(saved) !== checksum) {
          console.warn('[SellStrategy] 规则校验失败，使用默认值');
          this._rules = JSON.parse(JSON.stringify(DEFAULT_RULES));
        } else {
          this._rules = JSON.parse(saved);
        }
      } else {
        this._rules = JSON.parse(JSON.stringify(DEFAULT_RULES));
      }
    } catch (e) {
      console.warn('[SellStrategy] 加载规则失败:', e);
      this._rules = JSON.parse(JSON.stringify(DEFAULT_RULES));
    }
    // 确保所有字段存在
    if (!this._rules.peThreshold) this._rules.peThreshold = JSON.parse(JSON.stringify(DEFAULT_RULES.peThreshold));
    if (!this._rules.profitThreshold) this._rules.profitThreshold = JSON.parse(JSON.stringify(DEFAULT_RULES.profitThreshold));
  };

  SellStrategy.prototype._saveRules = function () {
    try {
      var json = JSON.stringify(this._rules);
      localStorage.setItem(STORAGE_KEY, json);
      localStorage.setItem(CHECKSUM_KEY, computeChecksum(json));
    } catch (e) {
      console.error('[SellStrategy] 保存规则失败:', e);
    }
  };

  // --- 数据持久化：已忽略的提醒 ---
  SellStrategy.prototype._loadDismissedAlerts = function () {
    try {
      var saved = localStorage.getItem('nasdaq_dca_dismissed_alerts');
      if (saved) {
        this._dismissedAlerts = JSON.parse(saved);
      }
    } catch (e) {
      this._dismissedAlerts = [];
    }
  };

  SellStrategy.prototype._saveDismissedAlerts = function () {
    try {
      localStorage.setItem('nasdaq_dca_dismissed_alerts', JSON.stringify(this._dismissedAlerts));
    } catch (e) {
      console.error('[SellStrategy] 保存忽略记录失败:', e);
    }
  };

  // --- 获取当前PE ---
  SellStrategy.prototype._getCurrentPE = function () {
    if (typeof marketData !== 'undefined' && marketData && marketData.pe) {
      return marketData.pe;
    }
    return 0;
  };

  // --- 获取当前价格 ---
  SellStrategy.prototype._getCurrentPrice = function () {
    if (typeof marketData !== 'undefined' && marketData && marketData.ndx) {
      return marketData.ndx.price || 0;
    }
    return 0;
  };

  // ===== 止盈规则检测 =====
  SellStrategy.prototype.checkSellSignals = function () {
    this._alerts = [];
    var currentPE = this._getCurrentPE();
    var currentPrice = this._getCurrentPrice();

    // --- PE阈值规则 ---
    if (this._rules.peThreshold.enabled && currentPE > 0) {
      var peRule = this._rules.peThreshold;

      if (currentPE >= peRule.peLevel3) {
        this._alerts.push({
          id: 'pe_level3_' + formatDateStr(new Date()),
          type: 'pe',
          severity: 'danger',
          title: 'PE严重高估 - 强烈建议减仓',
          message: '当前PE ' + currentPE.toFixed(2) + '，远超 ' + peRule.peLevel3 + ' 阈值。市场估值严重偏高，建议减仓 ' + peRule.reducePercent2 + '%。',
          pe: currentPE,
          threshold: peRule.peLevel3,
          reducePercent: peRule.reducePercent2,
          action: 'reduce'
        });
      } else if (currentPE >= peRule.peLevel2) {
        this._alerts.push({
          id: 'pe_level2_' + formatDateStr(new Date()),
          type: 'pe',
          severity: 'warning',
          title: 'PE高估 - 建议减仓',
          message: '当前PE ' + currentPE.toFixed(2) + '，超过 ' + peRule.peLevel2 + ' 阈值。市场估值偏高，建议减仓 ' + peRule.reducePercent1 + '%。',
          pe: currentPE,
          threshold: peRule.peLevel2,
          reducePercent: peRule.reducePercent1,
          action: 'reduce'
        });
      } else if (currentPE >= peRule.peLevel1) {
        this._alerts.push({
          id: 'pe_level1_' + formatDateStr(new Date()),
          type: 'pe',
          severity: 'info',
          title: 'PE偏高 - 关注市场',
          message: '当前PE ' + currentPE.toFixed(2) + '，超过 ' + peRule.peLevel1 + '。市场估值开始偏高，建议关注并做好减仓准备。',
          pe: currentPE,
          threshold: peRule.peLevel1,
          reducePercent: 0,
          action: 'watch'
        });
      }
    }

    // --- 收益率规则 ---
    if (this._rules.profitThreshold.enabled && window.PortfolioManager) {
      var positions = window.PortfolioManager.getPositions();
      var profitRule = this._rules.profitThreshold;

      for (var i = 0; i < positions.length; i++) {
        var pos = positions[i];
        var calc = window.PortfolioManager.calculateMarketValue(pos);

        if (calc.profitRate >= profitRule.strongTakeProfitRate) {
          this._alerts.push({
            id: 'profit_strong_' + pos.id + '_' + formatDateStr(new Date()),
            type: 'profit',
            severity: 'danger',
            title: '大额盈利 - 强烈建议止盈',
            message: (pos.fundName || pos.fundCode) + ' 收益率达 ' + formatPercent(calc.profitRate) + '，盈利 $' + formatMoney(calc.profit) + '。建议止盈卖出 ' + profitRule.reducePercent + '% 份额。',
            positionId: pos.id,
            fundCode: pos.fundCode,
            fundName: pos.fundName,
            profitRate: calc.profitRate,
            profit: calc.profit,
            reducePercent: profitRule.reducePercent,
            currentPrice: currentPrice,
            action: 'sell'
          });
        } else if (calc.profitRate >= profitRule.takeProfitRate) {
          this._alerts.push({
            id: 'profit_' + pos.id + '_' + formatDateStr(new Date()),
            type: 'profit',
            severity: 'warning',
            title: '达到止盈线 - 建议止盈',
            message: (pos.fundName || pos.fundCode) + ' 收益率达 ' + formatPercent(calc.profitRate) + '，盈利 $' + formatMoney(calc.profit) + '。已达到止盈线 ' + formatPercent(profitRule.takeProfitRate) + '，考虑分批止盈。',
            positionId: pos.id,
            fundCode: pos.fundCode,
            fundName: pos.fundName,
            profitRate: calc.profitRate,
            profit: calc.profit,
            reducePercent: 50,
            currentPrice: currentPrice,
            action: 'sell'
          });
        }
      }
    }

    return this._alerts;
  };

  // ===== 执行卖出 =====
  SellStrategy.prototype.executeSell = function (alertInfo, customShares) {
    if (!alertInfo || !window.PortfolioManager) return null;

    var currentPrice = this._getCurrentPrice();
    if (currentPrice <= 0) {
      alert('无法获取当前价格，请稍后再试');
      return null;
    }

    var sellShares = customShares || 0;
    var sellReason = '';

    if (alertInfo.type === 'pe') {
      // PE减仓：按比例减仓所有持仓
      var positions = window.PortfolioManager.getPositions();
      var totalSold = 0;
      var totalProfit = 0;
      var reducePercent = alertInfo.reducePercent / 100;

      for (var i = 0; i < positions.length; i++) {
        var pos = positions[i];
        var calc = window.PortfolioManager.calculateMarketValue(pos);
        var sharesToSell = pos.shares * reducePercent;
        if (sharesToSell <= 0) continue;

        var sellAmount = sharesToSell * currentPrice;
        var costBasis = (pos.buyAmount / pos.shares) * sharesToSell;
        var profit = sellAmount - costBasis;
        var profitRate = costBasis > 0 ? profit / costBasis : 0;

        window.PortfolioManager.addSellRecord({
          positionId: pos.id,
          fundCode: pos.fundCode,
          fundName: pos.fundName,
          sellDate: formatDateStr(new Date()),
          sellShares: sharesToSell,
          sellPrice: currentPrice,
          sellAmount: sellAmount,
          sellReason: 'PE减仓(PE=' + (alertInfo.pe || this._getCurrentPE()).toFixed(2) + ')',
          profit: profit,
          profitRate: profitRate
        });

        totalSold += sellAmount;
        totalProfit += profit;
      }

      return {
        totalSold: totalSold,
        totalProfit: totalProfit,
        reason: 'PE减仓'
      };
    } else if (alertInfo.type === 'profit') {
      // 收益率止盈：卖出指定持仓
      var position = null;
      var allPositions = window.PortfolioManager.getPositions();
      for (var j = 0; j < allPositions.length; j++) {
        if (allPositions[j].id === alertInfo.positionId) {
          position = allPositions[j];
          break;
        }
      }

      if (!position) {
        alert('找不到对应持仓');
        return null;
      }

      if (sellShares <= 0) {
        sellShares = position.shares * (alertInfo.reducePercent / 100);
      }

      var sellAmt = sellShares * currentPrice;
      var costPerShare = position.buyAmount / position.shares;
      var sellCost = costPerShare * sellShares;
      var sellProfit = sellAmt - sellCost;
      var sellProfitRate = sellCost > 0 ? sellProfit / sellCost : 0;

      var record = window.PortfolioManager.addSellRecord({
        positionId: position.id,
        fundCode: position.fundCode,
        fundName: position.fundName,
        sellDate: formatDateStr(new Date()),
        sellShares: sellShares,
        sellPrice: currentPrice,
        sellAmount: sellAmt,
        sellReason: alertInfo.title || '止盈卖出',
        profit: sellProfit,
        profitRate: sellProfitRate
      });

      return record;
    }

    return null;
  };

  // ===== 忽略提醒 =====
  SellStrategy.prototype.dismissAlert = function (alertId) {
    if (alertId) {
      this._dismissedAlerts.push(alertId);
      this._saveDismissedAlerts();
    }
  };

  SellStrategy.prototype.isAlertDismissed = function (alertId) {
    return this._dismissedAlerts.indexOf(alertId) !== -1;
  };

  // ===== 获取规则 =====
  SellStrategy.prototype.getRules = function () {
    return JSON.parse(JSON.stringify(this._rules));
  };

  // ===== 更新规则 =====
  SellStrategy.prototype.updateRules = function (newRules) {
    if (newRules.peThreshold) {
      for (var key in newRules.peThreshold) {
        if (newRules.peThreshold.hasOwnProperty(key)) {
          this._rules.peThreshold[key] = newRules.peThreshold[key];
        }
      }
    }
    if (newRules.profitThreshold) {
      for (var key2 in newRules.profitThreshold) {
        if (newRules.profitThreshold.hasOwnProperty(key2)) {
          this._rules.profitThreshold[key2] = newRules.profitThreshold[key2];
        }
      }
    }
    this._saveRules();
  };

  // ===== 渲染止盈提醒 =====
  SellStrategy.prototype.renderSellAlert = function () {
    var container = document.getElementById('sellAlertContainer');
    if (!container) {
      // 尝试在今日Tab中插入
      var todayTab = document.getElementById('tab-today');
      if (todayTab) {
        container = document.createElement('div');
        container.id = 'sellAlertContainer';
        container.style.marginTop = '12px';
        todayTab.appendChild(container);
      } else {
        console.warn('[SellStrategy] 找不到渲染容器');
        return;
      }
    }

    var alerts = this.checkSellSignals();
    var html = '';

    // 过滤已忽略的提醒
    var activeAlerts = [];
    for (var i = 0; i < alerts.length; i++) {
      if (!this.isAlertDismissed(alerts[i].id)) {
        activeAlerts.push(alerts[i]);
      }
    }

    if (activeAlerts.length === 0) {
      // 无提醒时显示状态
      var currentPE = this._getCurrentPE();
      var peStatus = '';
      if (currentPE > 0) {
        if (currentPE < 25) {
          peStatus = 'PE=' + currentPE.toFixed(2) + ' 估值偏低，继续定投';
        } else if (currentPE < 35) {
          peStatus = 'PE=' + currentPE.toFixed(2) + ' 估值正常，正常定投';
        } else {
          peStatus = 'PE=' + currentPE.toFixed(2) + ' 估值偏高，注意风险';
        }
      }

      html += '<div class="card" style="border:1px solid rgba(34,197,94,0.2);padding:12px;">';
      html += '  <div style="display:flex;align-items:center;gap:8px;">';
      html += '    <div style="font-size:20px;">✅</div>';
      html += '    <div>';
      html += '      <div style="font-size:13px;font-weight:600;color:var(--accent-green);">暂无止盈提醒</div>';
      if (peStatus) {
        html += '      <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">' + peStatus + '</div>';
      }
      html += '    </div>';
      html += '  </div>';
      html += '</div>';
    } else {
      for (var j = 0; j < activeAlerts.length; j++) {
        var alert = activeAlerts[j];
        var severityClass = alert.severity === 'danger' ? 'danger' : alert.severity === 'warning' ? 'warning' : 'info';
        var icon = alert.severity === 'danger' ? '🔴' : alert.severity === 'warning' ? '🟡' : '🔵';
        var borderColor = alert.severity === 'danger' ? 'rgba(239,68,68,0.4)' : alert.severity === 'warning' ? 'rgba(234,179,8,0.4)' : 'rgba(59,130,246,0.4)';
        var textColor = alert.severity === 'danger' ? 'var(--accent-red)' : alert.severity === 'warning' ? 'var(--accent-yellow)' : 'var(--accent-blue)';

        html += '<div class="card" style="border:2px solid ' + borderColor + ';padding:14px;margin-bottom:10px;">';
        html += '  <div style="display:flex;justify-content:space-between;align-items:flex-start;">';
        html += '    <div style="flex:1;">';
        html += '      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">';
        html += '        <span style="font-size:18px;">' + icon + '</span>';
        html += '        <span style="font-size:14px;font-weight:700;color:' + textColor + ';">' + alert.title + '</span>';
        html += '      </div>';
        html += '      <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;">' + alert.message + '</div>';

        // 显示操作按钮
        if (alert.action === 'reduce' || alert.action === 'sell') {
          var btnLabel = alert.action === 'sell' ? '执行卖出' : '执行减仓';
          html += '      <div style="display:flex;gap:8px;margin-top:10px;">';
          html += '        <button onclick="SellStrategy._handleAction(\'' + alert.id + '\')" style="padding:8px 16px;background:' + textColor + ';color:white;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">' + btnLabel + '</button>';
          html += '        <button onclick="SellStrategy.dismissAndRender(\'' + alert.id + '\')" style="padding:8px 16px;background:rgba(100,116,139,0.2);color:var(--text-secondary);border:none;border-radius:6px;font-size:12px;cursor:pointer;">忽略</button>';
          html += '      </div>';
        } else {
          html += '      <div style="margin-top:10px;">';
          html += '        <button onclick="SellStrategy.dismissAndRender(\'' + alert.id + '\')" style="padding:6px 12px;background:rgba(100,116,139,0.2);color:var(--text-secondary);border:none;border-radius:6px;font-size:11px;cursor:pointer;">知道了</button>';
          html += '      </div>';
        }

        html += '    </div>';
        html += '  </div>';
        html += '</div>';
      }
    }

    // --- 策略设置入口 ---
    html += '<div style="text-align:center;margin-top:8px;">';
    html += '  <button onclick="SellStrategy.showSettings()" style="padding:6px 12px;background:transparent;color:var(--text-muted);border:1px solid var(--border);border-radius:6px;font-size:11px;cursor:pointer;">止盈策略设置</button>';
    html += '</div>';

    container.innerHTML = html;
  };

  // ===== 操作处理 =====
  SellStrategy._handleAction = function (alertId) {
    var instance = window.SellStrategy;
    var alertInfo = null;
    var alerts = instance._alerts;
    for (var i = 0; i < alerts.length; i++) {
      if (alerts[i].id === alertId) {
        alertInfo = alerts[i];
        break;
      }
    }
    if (!alertInfo) return;

    if (alertInfo.action === 'sell' && alertInfo.positionId) {
      // 收益率止盈 - 确认卖出
      var confirmMsg = '确认卖出 ' + (alertInfo.fundName || alertInfo.fundCode) + ' 的 ' + alertInfo.reducePercent + '% 份额？\n';
      confirmMsg += '预估收益：' + formatPercent(alertInfo.profitRate) + ' ($' + formatMoney(alertInfo.profit) + ')';
      if (confirm(confirmMsg)) {
        var result = instance.executeSell(alertInfo);
        if (result) {
          instance.dismissAlert(alertId);
          instance.renderSellAlert();
          if (window.PortfolioManager) {
            window.PortfolioManager.renderPortfolio();
          }
        }
      }
    } else if (alertInfo.action === 'reduce') {
      // PE减仓 - 确认
      var reduceMsg = '当前PE=' + instance._getCurrentPE().toFixed(2) + '，确认按 ' + alertInfo.reducePercent + '% 比例减仓所有持仓？';
      if (confirm(reduceMsg)) {
        var reduceResult = instance.executeSell(alertInfo);
        if (reduceResult) {
          instance.dismissAlert(alertId);
          instance.renderSellAlert();
          if (window.PortfolioManager) {
            window.PortfolioManager.renderPortfolio();
          }
          alert('减仓完成！卖出总额 $' + formatMoney(reduceResult.totalSold) + '，收益 $' + formatMoney(reduceResult.totalProfit));
        }
      }
    }
  };

  // ===== 忽略并重新渲染 =====
  SellStrategy.dismissAndRender = function (alertId) {
    window.SellStrategy.dismissAlert(alertId);
    window.SellStrategy.renderSellAlert();
  };

  // ===== 设置面板 =====
  SellStrategy.showSettings = function () {
    var overlay = document.getElementById('sellStrategyOverlay');
    if (overlay) {
      overlay.classList.add('show');
      return;
    }

    var rules = window.SellStrategy.getRules();
    var peT = rules.peThreshold;
    var profT = rules.profitThreshold;

    overlay = document.createElement('div');
    overlay.id = 'sellStrategyOverlay';
    overlay.className = 'modal-overlay';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';

    overlay.innerHTML = '' +
      '<div style="background:var(--bg-card);border-radius:16px;padding:20px;width:90%;max-width:400px;max-height:80vh;overflow-y:auto;">' +
      '  <div style="font-size:16px;font-weight:700;margin-bottom:16px;">止盈策略设置</div>' +
      '' +
      '  <div class="section-divider">PE阈值规则</div>' +
      '  <div class="setting-group" style="display:flex;align-items:center;gap:8px;">' +
      '    <input id="ss_peEnabled" type="checkbox" ' + (peT.enabled ? 'checked' : '') + ' style="width:18px;height:18px;">' +
      '    <label for="ss_peEnabled" style="font-size:13px;">启用PE阈值规则</label>' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">关注阈值 (PE>)</div>' +
      '    <input id="ss_peLevel1" class="setting-input" type="number" step="1" value="' + peT.peLevel1 + '">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">减仓阈值 (PE>)</div>' +
      '    <input id="ss_peLevel2" class="setting-input" type="number" step="1" value="' + peT.peLevel2 + '">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">强减阈值 (PE>)</div>' +
      '    <input id="ss_peLevel3" class="setting-input" type="number" step="1" value="' + peT.peLevel3 + '">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">减仓比例 (%)</div>' +
      '    <input id="ss_reduceP1" class="setting-input" type="number" step="10" value="' + peT.reducePercent1 + '">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">强减比例 (%)</div>' +
      '    <input id="ss_reduceP2" class="setting-input" type="number" step="10" value="' + peT.reducePercent2 + '">' +
      '  </div>' +
      '' +
      '  <div class="section-divider">收益率止盈规则</div>' +
      '  <div class="setting-group" style="display:flex;align-items:center;gap:8px;">' +
      '    <input id="ss_profEnabled" type="checkbox" ' + (profT.enabled ? 'checked' : '') + ' style="width:18px;height:18px;">' +
      '    <label for="ss_profEnabled" style="font-size:13px;">启用收益率止盈规则</label>' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">止盈线 (收益率>)</div>' +
      '    <input id="ss_takeProfit" class="setting-input" type="number" step="5" value="' + (profT.takeProfitRate * 100) + '">' +
      '  </div>' +
      '  <div class="setting-group">' +
      '    <div class="setting-label">强止盈线 (收益率>)</div>' +
      '    <input id="ss_strongProfit" class="setting-input" type="number" step="5" value="' + (profT.strongTakeProfitRate * 100) + '">' +
      '  </div>' +
      '' +
      '  <div style="display:flex;gap:8px;margin-top:16px;">' +
      '    <button onclick="SellStrategy._closeSettings()" style="flex:1;padding:10px;background:rgba(100,116,139,0.2);color:var(--text-secondary);border:none;border-radius:8px;font-size:14px;cursor:pointer;">取消</button>' +
      '    <button onclick="SellStrategy._saveSettings()" style="flex:1;padding:10px;background:var(--accent-blue);color:white;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">保存</button>' +
      '  </div>' +
      '</div>';

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) SellStrategy._closeSettings();
    });

    document.body.appendChild(overlay);
  };

  SellStrategy._closeSettings = function () {
    var overlay = document.getElementById('sellStrategyOverlay');
    if (overlay) {
      overlay.classList.remove('show');
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
  };

  SellStrategy._saveSettings = function () {
    var newRules = {
      peThreshold: {
        enabled: document.getElementById('ss_peEnabled').checked,
        peLevel1: parseFloat(document.getElementById('ss_peLevel1').value) || 35,
        peLevel2: parseFloat(document.getElementById('ss_peLevel2').value) || 40,
        peLevel3: parseFloat(document.getElementById('ss_peLevel3').value) || 45,
        reducePercent1: parseFloat(document.getElementById('ss_reduceP1').value) || 50,
        reducePercent2: parseFloat(document.getElementById('ss_reduceP2').value) || 70
      },
      profitThreshold: {
        enabled: document.getElementById('ss_profEnabled').checked,
        takeProfitRate: (parseFloat(document.getElementById('ss_takeProfit').value) || 30) / 100,
        strongTakeProfitRate: (parseFloat(document.getElementById('ss_strongProfit').value) || 50) / 100,
        reducePercent: 100
      }
    };

    window.SellStrategy.updateRules(newRules);
    SellStrategy._closeSettings();
    window.SellStrategy.renderSellAlert();
    alert('止盈策略已保存');
  };

  // ===== 实例化并暴露到全局 =====
  var instance = new SellStrategy();
  window.SellStrategy = instance;

})();
