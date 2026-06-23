// ============================================================
// 纳指定投助手 - 核心引擎
// ============================================================

// ===== 配置 =====
const CONFIG = {
  CORS_PROXIES: [
    'https://corsproxy.io/?',
    'https://api.allorigins.win/raw?url=',
    'https://api.codetabs.com/v1/proxy?quest=',
  ],
  YAHOO_BASE: 'https://query1.finance.yahoo.com',
  SYMBOLS: {
    NDX: '^NDX',      // Nasdaq-100
    VIX: '^VIX',      // VIX恐慌指数
    TNX: '^TNX',      // 10年期美债收益率
    SPY: 'SPY',       // S&P 500 ETF (用于对比)
    QQQ: 'QQQ',       // Nasdaq-100 ETF
  },
  CACHE_DURATION: 5 * 60 * 1000, // 5分钟缓存
  USE_MOCK: false, // 强制使用模拟数据（调试用）
  // GitHub缓存路径（与index.html同目录）
  GITHUB_CACHE_URL: './cache.json',
  // 数据校验范围
  VALIDATION: {
    NDX_MIN: 5000,
    NDX_MAX: 50000,
    PE_MIN: 10,
    PE_MAX: 60,
    VIX_MIN: 5,
    VIX_MAX: 100,
  },
};

// ===== 用户设置（从当前角色生成）=====
let userSettings = {
  startDate: '',
  totalAssets: 1.0,
  holdings: 16,
};

// ===== 角色系统 =====
const DEFAULT_PROFILE = {
  id: 'default',
  name: '默认账户',
  startDate: '2026-06-01',
  frequency: 'weekly',
  method: 'pe-based',
  baseAmount: 1000,
  assetRatio: 1.0,
  holdings: 16,
  isDefault: true,
};

// 默认角色的初始记录
const DEFAULT_HISTORY_RECORD = {
  date: '2026-06-05',
  type: '周四定投',
  amount: 1000,
  shares: 1,
  pe: 33,
  ndx: 21000,
  profileId: 'default',
};

let profiles = [];
let currentProfileId = 'default';

// ===== 校验和工具 =====
function computeChecksum(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return hash.toString(16);
}

function loadProfiles() {
  try {
    const saved = localStorage.getItem('nasdaq_dca_profiles');
    const checksum = localStorage.getItem('nasdaq_dca_profiles_checksum');
    if (saved) {
      if (checksum && computeChecksum(saved) !== checksum) {
        console.warn('Profiles checksum mismatch, using defaults');
        profiles = [];
      } else {
        profiles = JSON.parse(saved);
      }
    }
  } catch (e) {
    console.warn('Profiles load failed:', e);
    profiles = [];
  }

  // 确保默认角色始终存在
  const hasDefault = profiles.find(p => p.id === 'default');
  if (!hasDefault) {
    profiles.unshift({ ...DEFAULT_PROFILE });
  }

  // 加载当前选中的角色ID
  try {
    const savedId = localStorage.getItem('nasdaq_dca_current_profile');
    if (savedId && profiles.find(p => p.id === savedId)) {
      currentProfileId = savedId;
    }
  } catch (e) {
    currentProfileId = 'default';
  }

  // 确保默认角色的初始记录存在
  ensureDefaultHistoryRecord();

  // 从当前角色生成 userSettings
  syncUserSettingsFromProfile();
}

function saveProfiles() {
  const data = JSON.stringify(profiles);
  localStorage.setItem('nasdaq_dca_profiles', data);
  localStorage.setItem('nasdaq_dca_profiles_checksum', computeChecksum(data));
  localStorage.setItem('nasdaq_dca_current_profile', currentProfileId);
}

function ensureDefaultHistoryRecord() {
  let allHistory = [];
  try {
    const saved = localStorage.getItem('nasdaq_dca_history');
    const checksum = localStorage.getItem('nasdaq_dca_history_checksum');
    if (saved) {
      if (checksum && computeChecksum(saved) !== checksum) {
        console.warn('History checksum mismatch, using empty');
        allHistory = [];
      } else {
        allHistory = JSON.parse(saved);
      }
    }
  } catch (e) {
    allHistory = [];
  }
  const exists = allHistory.find(h => h.date === '2026-06-05' && h.profileId === 'default');
  if (!exists) {
    allHistory.push({ ...DEFAULT_HISTORY_RECORD });
    const data = JSON.stringify(allHistory);
    localStorage.setItem('nasdaq_dca_history', data);
    localStorage.setItem('nasdaq_dca_history_checksum', computeChecksum(data));
  }
}

function getCurrentProfile() {
  return profiles.find(p => p.id === currentProfileId) || profiles[0] || { ...DEFAULT_PROFILE };
}

function syncUserSettingsFromProfile() {
  const profile = getCurrentProfile();
  userSettings = {
    startDate: profile.startDate,
    totalAssets: profile.assetRatio,
    holdings: profile.holdings || 16,
    frequency: profile.frequency || 'weekly',
    method: profile.method || 'pe-based',
    baseAmount: profile.baseAmount || 1000,
  };
}

function addProfile() {
  const newId = 'profile_' + Date.now();
  const newProfile = {
    id: newId,
    name: '新角色 ' + (profiles.length),
    startDate: new Date().toISOString().split('T')[0],
    frequency: 'weekly',
    method: 'pe-based',
    baseAmount: 1000,
    assetRatio: 1.0,
    holdings: 16,
    isDefault: false,
  };
  profiles.push(newProfile);
  saveProfiles();
  currentProfileId = newId;
  saveProfiles();
  syncUserSettingsFromProfile();
  renderProfileUI();
}

function deleteCurrentProfile() {
  const profile = getCurrentProfile();
  if (profile.isDefault) {
    alert('默认角色不可删除');
    return;
  }
  if (!confirm(`确定要删除角色"${profile.name}"吗？相关定投记录将保留。`)) return;

  profiles = profiles.filter(p => p.id !== currentProfileId);
  currentProfileId = 'default';
  saveProfiles();
  syncUserSettingsFromProfile();
  renderProfileUI();

  // 重新渲染
  if (marketData) {
    renderAllTabs(marketData);
  }
}

function switchProfile(profileId) {
  currentProfileId = profileId;
  saveProfiles();
  syncUserSettingsFromProfile();
  renderProfileUI();

  // 重新渲染
  if (marketData) {
    renderAllTabs(marketData);
  }
}

function saveCurrentProfile() {
  const profile = getCurrentProfile();
  profile.name = document.getElementById('profileName').value || profile.name;
  profile.startDate = document.getElementById('profileStartDate').value || profile.startDate;
  profile.frequency = document.getElementById('profileFrequency').value;
  profile.baseAmount = parseFloat(document.getElementById('profileBaseAmount').value) || 1000;
  profile.assetRatio = parseFloat(document.getElementById('profileAssetRatio').value) || 1.0;

  saveProfiles();
  syncUserSettingsFromProfile();

  // 更新下拉框显示
  const select = document.getElementById('profileSelect');
  const option = select.querySelector(`option[value="${profile.id}"]`);
  if (option) option.textContent = profile.name;

  // 重新渲染
  if (marketData) {
    renderAllTabs(marketData);
  }

  alert('角色已保存');
}

function renderProfileUI() {
  const select = document.getElementById('profileSelect');
  select.innerHTML = profiles.map(p =>
    `<option value="${p.id}" ${p.id === currentProfileId ? 'selected' : ''}>${p.name}${p.isDefault ? ' (默认)' : ''}</option>`
  ).join('');

  const profile = getCurrentProfile();
  document.getElementById('profileName').value = profile.name;
  document.getElementById('profileStartDate').value = profile.startDate;
  document.getElementById('profileFrequency').value = profile.frequency;
  document.getElementById('profileBaseAmount').value = profile.baseAmount || 1000;
  document.getElementById('profileAssetRatio').value = profile.assetRatio;

  // 更新Header角色名称
  const headerProfile = document.getElementById('headerProfile');
  if (headerProfile) {
    headerProfile.textContent = '👤 ' + profile.name;
  }

  // 默认角色不可删除
  const deleteBtn = document.getElementById('deleteProfileBtn');
  deleteBtn.style.display = profile.isDefault ? 'none' : 'block';
}

// ===== 全局状态 =====
let marketData = null;
let lastFetchTime = 0;
let currentProxyIndex = 0;
let consecutiveAddDays = 0;

// ===== Tab 顺序（用于手势和快捷键）=====
const TAB_ORDER = ['today', 'short', 'mid', 'long', 'history', 'help'];

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', async () => {
  try {
    loadProfiles();
    loadSettings();
    renderProfileUI();
    initTouchGestures();
    initKeyboardShortcuts();
    checkDisclaimer();

    // 速度优化：优先读GitHub缓存（秒开），再后台拉新数据
    try {
      const githubCache = await fetchGitHubCache();
      if (githubCache) {
        githubCache._source = 'github-cache';
        marketData = githubCache;
        renderAllTabs(githubCache);
        updateHeaderStatus(githubCache);
        document.getElementById('loadingState').style.display = 'none';
        // 后台静默尝试获取更新数据
        fetchAllMarketData().then(fresh => {
          if (fresh && !fresh._mock && !fresh._stale) {
            marketData = fresh;
            renderAllTabs(fresh);
            updateHeaderStatus(fresh);
          }
        }).catch(() => {});
        return; // 有缓存就不再走loading流程
      }
    } catch (e) {
      console.warn('GitHub cache fetch failed:', e);
    }

    // 无GitHub缓存，尝试localStorage缓存
    const localCached = loadCachedData();
    if (localCached) {
      localCached._source = 'local-cache';
      marketData = localCached;
      renderAllTabs(localCached);
      updateHeaderStatus(localCached);
      document.getElementById('loadingState').style.display = 'none';
      fetchAllMarketData().then(fresh => {
        if (fresh && !fresh._mock) {
          marketData = fresh;
          renderAllTabs(fresh);
          updateHeaderStatus(fresh);
        }
      }).catch(() => {});
      return;
    }

    // 完全无缓存，走完整加载
    await refreshData();
  } catch (err) {
    console.error('Initialization error:', err);
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('errorState').style.display = 'block';
    document.getElementById('errorMsg').textContent = '初始化失败: ' + (err.message || '未知错误');
    const statusBadge = document.getElementById('statusBadge');
    const statusText = document.getElementById('statusText');
    if (statusBadge) statusBadge.className = 'status-badge error';
    if (statusText) statusText.textContent = '错误';
  }
});

// ===== 免责声明 =====
function checkDisclaimer() {
  try {
    const accepted = localStorage.getItem('nasdaq_dca_disclaimer_accepted');
    if (!accepted) {
      document.getElementById('disclaimerModal').classList.add('show');
    }
  } catch (e) {
    console.warn('Disclaimer check failed:', e);
  }
}

function acceptDisclaimer() {
  try {
    localStorage.setItem('nasdaq_dca_disclaimer_accepted', 'true');
    document.getElementById('disclaimerModal').classList.remove('show');
  } catch (e) {
    console.warn('Disclaimer accept failed:', e);
  }
}

// ===== 导出/导入数据 =====
function exportData() {
  try {
    const exportObj = {
      version: '1.0',
      exportedAt: new Date().toISOString(),
      profiles: JSON.parse(localStorage.getItem('nasdaq_dca_profiles') || '[]'),
      currentProfileId: localStorage.getItem('nasdaq_dca_current_profile') || 'default',
      history: JSON.parse(localStorage.getItem('nasdaq_dca_history') || '[]'),
      settings: JSON.parse(localStorage.getItem('nasdaq_dca_settings') || '{}'),
      cache: JSON.parse(localStorage.getItem('nasdaq_dca_cache') || '{}'),
    };
    const blob = new Blob([JSON.stringify(exportObj, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nasdaq-dca-backup-${formatDateStr(new Date())}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    alert('数据已导出');
  } catch (e) {
    console.error('Export failed:', e);
    alert('导出失败: ' + e.message);
  }
}

function importData() {
  document.getElementById('importFileInput').click();
}

function handleImportFile(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const data = JSON.parse(e.target.result);
      if (!data.profiles || !Array.isArray(data.profiles)) {
        throw new Error('无效的数据文件');
      }

      if (!confirm('导入将覆盖当前所有数据，确定继续吗？')) return;

      localStorage.setItem('nasdaq_dca_profiles', JSON.stringify(data.profiles));
      localStorage.setItem('nasdaq_dca_profiles_checksum', computeChecksum(JSON.stringify(data.profiles)));
      if (data.currentProfileId) {
        localStorage.setItem('nasdaq_dca_current_profile', data.currentProfileId);
      }
      if (data.history) {
        const historyStr = JSON.stringify(data.history);
        localStorage.setItem('nasdaq_dca_history', historyStr);
        localStorage.setItem('nasdaq_dca_history_checksum', computeChecksum(historyStr));
      }
      if (data.settings) {
        localStorage.setItem('nasdaq_dca_settings', JSON.stringify(data.settings));
      }
      if (data.cache) {
        localStorage.setItem('nasdaq_dca_cache', JSON.stringify(data.cache));
      }

      // 重新加载
      loadProfiles();
      loadSettings();
      renderProfileUI();
      renderHistoryTab();
      if (marketData) renderAllTabs(marketData);

      alert('数据导入成功');
    } catch (err) {
      console.error('Import failed:', err);
      alert('导入失败: ' + err.message);
    }
  };
  reader.readAsText(file);
  event.target.value = '';
}

// ===== 手势操作 =====
function initTouchGestures() {
  let startX = 0;
  let startY = 0;
  let isScrolling = false;

  document.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    isScrolling = false;
  }, { passive: true });

  document.addEventListener('touchmove', (e) => {
    if (isScrolling) return;
    const dx = Math.abs(e.touches[0].clientX - startX);
    const dy = Math.abs(e.touches[0].clientY - startY);
    if (dy > dx && dy > 10) {
      isScrolling = true;
    }
  }, { passive: true });

  document.addEventListener('touchend', (e) => {
    if (isScrolling) return;
    const endX = e.changedTouches[0].clientX;
    const diffX = endX - startX;
    const threshold = 50;

    if (Math.abs(diffX) > threshold) {
      const activeTab = document.querySelector('.tab-btn.active');
      const currentIndex = TAB_ORDER.findIndex(t => {
        const btn = document.querySelector(`.tab-btn[onclick*="'${t}'"]`);
        return btn && btn.classList.contains('active');
      });

      if (currentIndex === -1) return;

      let nextIndex;
      if (diffX < 0) {
        nextIndex = Math.min(currentIndex + 1, TAB_ORDER.length - 1);
      } else {
        nextIndex = Math.max(currentIndex - 1, 0);
      }

      if (nextIndex !== currentIndex) {
        const nextTab = TAB_ORDER[nextIndex];
        const nextBtn = document.querySelector(`.tab-btn[onclick*="'${nextTab}'"]`);
        if (nextBtn) {
          switchTab(nextTab, nextBtn);
        }
      }
    }
  }, { passive: true });

  // 首次使用显示滑动提示
  try {
    const hintShown = localStorage.getItem('nasdaq_dca_swipe_hint_shown');
    if (!hintShown) {
      const hint = document.createElement('div');
      hint.className = 'swipe-hint';
      hint.textContent = '左右滑动切换Tab';
      document.body.appendChild(hint);
      localStorage.setItem('nasdaq_dca_swipe_hint_shown', 'true');
      setTimeout(() => {
        if (hint.parentNode) hint.parentNode.removeChild(hint);
      }, 4500);
    }
  } catch (e) {
    console.warn('Swipe hint failed:', e);
  }
}

// ===== 键盘快捷键 =====
function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // 忽略输入框中的按键
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
      return;
    }

    const key = e.key.toLowerCase();

    // 1-6 切换Tab
    if (key >= '1' && key <= '6') {
      const index = parseInt(key, 10) - 1;
      if (index < TAB_ORDER.length) {
        const tabName = TAB_ORDER[index];
        const btn = document.querySelector(`.tab-btn[onclick*="'${tabName}'"]`);
        if (btn) switchTab(tabName, btn);
      }
      return;
    }

    switch (key) {
      case 'r':
        e.preventDefault();
        refreshData();
        break;
      case 's':
        e.preventDefault();
        toggleSettings();
        break;
      case 'escape':
        closeSettings();
        // 关闭弹窗
        document.querySelectorAll('.modal-overlay.show').forEach(m => m.classList.remove('show'));
        break;
      case 'h':
        e.preventDefault();
        const helpBtn = document.querySelector(`.tab-btn[onclick*="'help'"]`);
        if (helpBtn) switchTab('help', helpBtn);
        break;
    }
  });
}

// 读取GitHub上的cache.json
async function fetchGitHubCache() {
  try {
    const response = await fetch(CONFIG.GITHUB_CACHE_URL);
    if (!response.ok) return null;
    const data = await response.json();
    // 检查数据是否过期（超过2小时视为过期，但仍显示）
    const age = Date.now() - new Date(data.updatedAt || data.timestamp).getTime();
    if (age > 7 * 24 * 60 * 60 * 1000) return null; // 超过7天不用（非交易时段缓存保留更久）
    // 解析nyTime为Date对象
    if (typeof data.nyTime === 'string') {
      data.nyTime = new Date(data.nyTime);
    }
    return data;
  } catch (e) {
    return null;
  }
}

// 渲染所有Tab的统一入口
function renderAllTabs(data) {
  const activeTab = document.querySelector('.tab-content.active');
  if (!activeTab) {
    document.getElementById('tab-today').classList.add('active');
  }
  renderTodayTab(data);
  renderShortTermTab(data);
  renderMidTermTab(data);
  renderLongTermTab(data);
  renderHistoryTab();
}

// 更新头部状态
function updateHeaderStatus(data) {
  const statusBadge = document.getElementById('statusBadge');
  const statusText = document.getElementById('statusText');
  const headerTime = document.getElementById('headerTime');

  if (data._mock) {
    statusBadge.className = 'status-badge loading';
    statusText.textContent = '演示数据';
  } else if (data._stale) {
    statusBadge.className = 'status-badge loading';
    statusText.textContent = '缓存数据';
  } else {
    statusBadge.className = 'status-badge live';
    statusText.textContent = '实时';
  }

  const nyTime = data.nyTime;
  const dataSource = data._mock ? ' [演示模式]' : data._stale ? ' [缓存模式]' : '';
  headerTime.textContent = `美东时间 ${formatTime(nyTime)} ${getDayName(nyTime.getDay())} | 更新于 ${formatTime(new Date())}${dataSource}`;
}

// ===== 数据获取层 =====

async function fetchViaProxy(url, timeoutMs = 6000) {
  // 尝试所有代理，每个有独立超时
  for (let i = 0; i < CONFIG.CORS_PROXIES.length; i++) {
    const proxyUrl = CONFIG.CORS_PROXIES[(currentProxyIndex + i) % CONFIG.CORS_PROXIES.length] + encodeURIComponent(url);
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      const response = await fetch(proxyUrl, {
        headers: { 'Accept': 'application/json' },
        signal: controller.signal
      });
      clearTimeout(timer);
      if (response.ok) {
        currentProxyIndex = (currentProxyIndex + i) % CONFIG.CORS_PROXIES.length;
        const data = await response.json();
        // 数据校验
        if (!validateApiResponse(data, url)) {
          console.warn('API response validation failed for', url);
          throw new Error('数据校验失败');
        }
        return data;
      }
    } catch (e) {
      console.warn(`Proxy ${i} failed:`, e.message);
    }
  }
  throw new Error('所有代理均无法连接');
}

function validateApiResponse(data, url) {
  if (!data || typeof data !== 'object') return false;
  // Yahoo chart API 校验
  if (url.includes('/v8/finance/chart/')) {
    const result = data.chart?.result?.[0];
    if (!result) return false;
    const meta = result.meta;
    if (!meta) return false;
    const price = meta.regularMarketPrice;
    // NDX 价格范围校验
    if (url.includes('^NDX') || url.includes('%5ENDX')) {
      if (typeof price !== 'number' || price < CONFIG.VALIDATION.NDX_MIN || price > CONFIG.VALIDATION.NDX_MAX) {
        console.warn(`NDX price validation failed: ${price}`);
        return false;
      }
    }
    // VIX 范围校验
    if (url.includes('^VIX') || url.includes('%5EVIX')) {
      if (typeof price !== 'number' || price < CONFIG.VALIDATION.VIX_MIN || price > CONFIG.VALIDATION.VIX_MAX) {
        console.warn(`VIX validation failed: ${price}`);
        return false;
      }
    }
  }
  return true;
}

async function fetchChartData(symbol, range = '5d', interval = '1d') {
  const url = `${CONFIG.YAHOO_BASE}/v8/finance/chart/${symbol}?interval=${interval}&range=${range}`;
  try {
    return await fetchViaProxy(url);
  } catch (e) {
    console.warn('fetchChartData failed, trying cache fallback:', e);
    // 尝试回退到缓存
    const cached = loadCachedData();
    if (cached) {
      cached._stale = true;
      return cached;
    }
    throw e;
  }
}

async function fetchMultipleQuotes(symbols) {
  const url = `${CONFIG.YAHOO_BASE}/v8/finance/spark?symbols=${symbols.join(',')}&range=1d&interval=5m`;
  return fetchViaProxy(url);
}

// 获取PE数据 - 多数据源
async function fetchPEData() {
  // 方法1: 从QQQ的stats获取近似PE
  try {
    const data = await fetchChartData('QQQ', '1mo', '1d');
    const meta = data.chart?.result?.[0]?.meta;
    // Yahoo chart API 不直接给PE，需要用备用方案
  } catch (e) {
    console.warn('QQQ data fetch failed:', e);
  }

  // 方法2: 从Siblis Research获取
  try {
    const url = 'https://siblisresearch.com/data/nasdaq-100-pe-ratio/';
    const proxyUrl = CONFIG.CORS_PROXIES[currentProxyIndex] + encodeURIComponent(url);
    const response = await fetch(proxyUrl);
    if (response.ok) {
      const html = await response.text();
      // 解析HTML表格获取最新PE
      const peMatch = html.match(/([\d.]+)\s*<\/td>\s*<td[^>]*>[\d.]+\s*<\/td>\s*<td[^>]*>([\d.]+)\s*<\/td>/);
      if (peMatch) {
        const pe = parseFloat(peMatch[2]);
        if (pe >= CONFIG.VALIDATION.PE_MIN && pe <= CONFIG.VALIDATION.PE_MAX) {
          return pe;
        }
      }
    }
  } catch (e) {
    console.warn('Siblis PE fetch failed:', e);
  }

  // 方法3: 使用内置的PE估算（基于NDX价格和已知PE关系）
  return null;
}

// ===== 主数据获取函数 =====

async function fetchAllMarketData() {
  const now = Date.now();

  // 如果强制使用模拟数据或缓存中有数据
  if (CONFIG.USE_MOCK) {
    return generateMockData();
  }

  // 尝试从缓存加载
  const cached = loadCachedData();
  if (cached && (now - cached.timestamp < CONFIG.CACHE_DURATION)) {
    return cached;
  }

  try {
    // 并行获取所有数据
    const [ndxData, vixData, tnxData, spyData] = await Promise.all([
      fetchChartData(CONFIG.SYMBOLS.NDX, '1mo', '1d'),
      fetchChartData(CONFIG.SYMBOLS.VIX, '5d', '1d'),
      fetchChartData(CONFIG.SYMBOLS.TNX, '5d', '1d'),
      fetchChartData(CONFIG.SYMBOLS.SPY, '1mo', '1d'),
    ]);

  // 解析NDX数据
  const ndxResult = ndxData.chart?.result?.[0];
  const ndxMeta = ndxResult?.meta;
  const ndxQuotes = ndxResult?.indicators?.quote?.[0];
  const timestamps = ndxResult?.timestamp || [];
  const closes = ndxQuotes?.close || [];

  // 获取最近20个交易日的收盘价（用于均线计算）
  const recentCloses = closes.filter(c => c !== null).slice(-20);
  const ma20 = recentCloses.length >= 20
    ? recentCloses.slice(-20).reduce((a, b) => a + b, 0) / 20
    : recentCloses.reduce((a, b) => a + b, 0) / recentCloses.length;

  // 解析VIX
  const vixMeta = vixData.chart?.result?.[0]?.meta;
  const vixQuotes = vixData.chart?.result?.[0]?.indicators?.quote?.[0];
  const vixCloses = vixQuotes?.close?.filter(c => c !== null) || [];

  // 解析10Y美债
  const tnxMeta = tnxData.chart?.result?.[0]?.meta;

  // 解析SPY
  const spyMeta = spyData.chart?.result?.[0]?.meta;
  const spyQuotes = spyData.chart?.result?.[0]?.indicators?.quote?.[0];
  const spyCloses = spyQuotes?.close?.filter(c => c !== null) || [];

  // 获取PE数据
  let pe = await fetchPEData();

  // 如果PE获取失败，使用估算
  if (!pe) {
    pe = estimatePE(ndxMeta?.regularMarketPrice);
  }

  // PE范围校验
  if (pe < CONFIG.VALIDATION.PE_MIN || pe > CONFIG.VALIDATION.PE_MAX) {
    console.warn(`PE validation failed: ${pe}, using estimate`);
    pe = estimatePE(ndxMeta?.regularMarketPrice);
  }

  // 计算近期高点
  const allCloses = closes.filter(c => c !== null);
  const recentHigh = Math.max(...allCloses.slice(-60)); // 60日内高点
  const drawdown = ((recentHigh - ndxMeta.regularMarketPrice) / recentHigh * 100);

  // 前一交易日涨跌幅
  const prevClose = ndxMeta?.chartPreviousClose || ndxMeta?.previousClose;
  const currentPrice = ndxMeta?.regularMarketPrice;
  const dailyChange = prevClose ? ((currentPrice - prevClose) / prevClose * 100) : 0;

  // 周涨跌幅
  const weekAgoCloses = allCloses.slice(-7, -1);
  const weekStart = weekAgoCloses.length > 0 ? weekAgoCloses[0] : allCloses[allCloses.length - 6] || currentPrice;
  const weeklyChange = ((currentPrice - weekStart) / weekStart * 100);

  // 判断交易日/非交易日
  const today = getNYTime();
  const dayOfWeek = today.getDay();
  const isTradingDay = dayOfWeek >= 1 && dayOfWeek <= 5;
  const isThursday = dayOfWeek === 4;

  // 根据定投频率判断是否为定投日
  const frequency = (getCurrentProfile()).frequency || 'weekly';
  let isDCAday = false;
  if (frequency === 'daily') {
    isDCAday = isTradingDay;
  } else {
    isDCAday = isThursday;
  }

  // 计算距下次定投日天数
  let daysToDCA = 0;
  if (frequency === 'daily') {
    daysToDCA = isTradingDay ? 0 : (dayOfWeek === 0 ? 1 : (dayOfWeek === 6 ? 1 : 0));
  } else {
    daysToDCA = (4 - dayOfWeek + 7) % 7;
    if (daysToDCA === 0 && isTradingDay) daysToDCA = 0;
    else if (daysToDCA === 0) daysToDCA = 7;
  }

  // 股债性价比（简化：美债收益率 vs 标普收益率倒数）
  const spyYield = spyMeta?.regularMarketPrice ? 1 / (spyMeta.regularMarketPrice / 100) : 0;
  const bondYield = tnxMeta?.regularMarketPrice || 0;
  const equityBondRatio = bondYield > 0 ? (spyYield / bondYield).toFixed(2) : '--';

  // 获取历史PE数据用于趋势分析
  const historicalPE = generateHistoricalPE(pe, allCloses);

  marketData = {
    timestamp: now,
    nyTime: today,

    // 价格数据
    ndx: {
      price: currentPrice,
      prevClose: prevClose,
      change: dailyChange,
      weeklyChange: weeklyChange,
      high60d: recentHigh,
      drawdown: drawdown,
      ma20: ma20,
      ma20Direction: currentPrice > ma20 ? 'up' : 'down',
      recentCloses: allCloses.slice(-30),
      timestamps: timestamps.slice(-30),
    },

    // 估值
    pe: pe,
    peGrade: getPEGrade(pe),

    // 恐慌指标
    vix: vixCloses.length > 0 ? vixCloses[vixCloses.length - 1] : null,
    vixRecent: vixCloses.slice(-5),

    // 美债
    treasury10y: tnxMeta?.regularMarketPrice || null,

    // 股债性价比
    equityBondRatio: equityBondRatio,

    // 日期信息
    isTradingDay: isTradingDay,
    isThursday: isThursday,
    isDCAday: isDCAday,
    frequency: frequency,
    daysToDCA: daysToDCA,
    dayOfWeek: dayOfWeek,

    // 历史PE
    historicalPE: historicalPE,
  };

  lastFetchTime = now;
  saveCachedData(marketData);
  return marketData;

  } catch (err) {
    console.error('Fetch failed, trying fallback:', err);

    // 尝试使用过期缓存
    const staleCached = loadCachedData();
    if (staleCached) {
      console.log('Using stale cached data');
      staleCached._stale = true;
      return staleCached;
    }

    // 最终降级：使用模拟数据
    console.log('Using mock data as final fallback');
    const mockData = generateMockData();
    mockData._mock = true;
    return mockData;
  }
}

// ===== PE估算函数 =====
function estimatePE(price) {
  // 基于已知数据点进行线性插值估算
  // 数据点：(价格, PE) - 覆盖2020-2025年关键价格-PE对应关系
  const knownPoints = [
    [7500, 22.5],   // 2020-03
    [11000, 30.2],  // 2020-09
    [13000, 32.5],  // 2021-01
    [14500, 28.8],  // 2021-07
    [15000, 25.5],  // 2022-01
    [10500, 20.8],  // 2022-10
    [10500, 23.5],  // 2023-01
    [15500, 29.0],  // 2023-07
    [17000, 28.5],  // 2024-01
    [19000, 30.5],  // 2024-07
    [21000, 33.0],  // 2025-01
    [22000, 34.5],  // 2025-06
  ];

  if (!price) return 30; // 默认值

  // 找到最近的两个数据点进行插值
  knownPoints.sort((a, b) => a[0] - b[0]);

  for (let i = 0; i < knownPoints.length - 1; i++) {
    if (price >= knownPoints[i][0] && price <= knownPoints[i + 1][0]) {
      const ratio = (price - knownPoints[i][0]) / (knownPoints[i + 1][0] - knownPoints[i][0]);
      return knownPoints[i][1] + ratio * (knownPoints[i + 1][1] - knownPoints[i][1]);
    }
  }

  // 超出范围时外推
  if (price < knownPoints[0][0]) {
    return knownPoints[0][1] - (knownPoints[0][0] - price) / 1000;
  }
  const last = knownPoints[knownPoints.length - 1];
  return last[1] + (price - last[0]) / 1000;
}

// 生成模拟历史PE数据（用于长期趋势展示）
function generateHistoricalPE(currentPE, closes) {
  // 基于价格反推历史PE的近似值（确定性算法，无随机数）
  const currentPrice = closes[closes.length - 1] || 20000;
  return closes.slice(-60).map((c, i) => {
    const priceRatio = c / currentPrice;
    // 用确定性正弦波模拟PE围绕价格比率的波动，替代原来的 Math.random()
    const deterministicFactor = 0.95 + 0.1 * Math.sin(i * 0.7);
    return Math.max(15, Math.min(50, currentPE * priceRatio * deterministicFactor));
  });
}

// 生成迷你走势图SVG（近20日收盘价）
function generateMiniChart(recentCloses) {
  const prices = recentCloses.filter(c => c !== null).slice(-20);
  if (prices.length < 2) return '';

  const width = 300;
  const height = 60;
  const padding = 4;

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;

  // 将价格映射到SVG坐标
  const points = prices.map((p, i) => {
    const x = padding + (i / (prices.length - 1)) * (width - 2 * padding);
    const y = height - padding - ((p - min) / range) * (height - 2 * padding);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const polylinePoints = points.join(' ');

  // 判断趋势：最后价格 vs 第一价格
  const isUp = prices[prices.length - 1] >= prices[0];
  const lineColor = isUp ? 'var(--accent-green)' : 'var(--accent-red)';
  const dotColor = isUp ? '#22c55e' : '#ef4444';

  // 最后一个点的坐标
  const lastPoint = points[points.length - 1];

  return `
    <div style="margin-top:12px;">
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">近20日收盘价走势</div>
      <svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" style="display:block;max-width:100%;">
        <polyline
          points="${polylinePoints}"
          fill="none"
          stroke="${lineColor}"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <circle cx="${lastPoint.split(',')[0]}" cy="${lastPoint.split(',')[1]}" r="3" fill="${dotColor}" />
      </svg>
    </div>
  `;
}


// ===== 金额格式化 =====
function formatAmount(shares) {
  const profile = getCurrentProfile();
  const baseAmount = profile.baseAmount || 1000;
  return Math.round(shares * baseAmount);
}

function formatAmountStr(shares) {
  return formatAmount(shares) + '元';
}

// ===== PE档位判定 =====
function getPEGrade(pe) {
  if (pe <= 25) return { level: '加倍', shares: 2, class: 'buy-double', color: 'green' };
  if (pe <= 28) return { level: '1.5倍', shares: 1.5, class: 'buy-normal', color: 'blue' };
  if (pe <= 32) return { level: '正常', shares: 1, class: 'buy-normal', color: 'blue' };
  if (pe <= 35) return { level: '半额', shares: 0.5, class: 'buy-half', color: 'yellow' };
  if (pe <= 40) return { level: '最低', shares: 0.3, class: 'buy-min', color: 'orange' };
  return { level: '暂停', shares: 0, class: 'buy-zero', color: 'red' };
}

// ===== 加仓判定（三步法）=====
function calculateAdditionalBuy(data) {
  // 每日定投模式下无额外加仓，定投日本身就是买入日
  if (!data.isTradingDay) {
    return { shouldAdd: false, shares: 0, reason: '今日非交易日' };
  }
  if (data.frequency === 'daily') {
    return { shouldAdd: false, shares: 0, reason: '每日定投模式，按PE档位自动执行' };
  }
  if (data.isThursday) {
    return { shouldAdd: false, shares: 0, reason: '周四禁止加仓' };
  }

  const change = data.ndx.change; // 前一交易日涨跌幅
  const pe = data.pe;
  const vix = data.vix;
  const weeklyChange = data.ndx.weeklyChange;

  // 第一步：跌幅判定
  let baseShares = 0;
  let step1Reason = '';
  if (change >= 0 || change > -2) {
    baseShares = 0;
    step1Reason = `前日涨跌幅${change >= 0 ? '+' : ''}${change.toFixed(2)}%，未触发加仓阈值`;
  } else if (change >= -4) {
    baseShares = 0.5;
    step1Reason = `前日跌${change.toFixed(2)}%，触发0.5倍档`;
  } else if (change >= -7) {
    baseShares = 1;
    step1Reason = `前日跌${change.toFixed(2)}%，触发1倍档`;
  } else {
    baseShares = 1;
    step1Reason = `前日跌${change.toFixed(2)}%，触发1倍档+极端超跌`;
  }

  if (baseShares === 0) {
    return { shouldAdd: false, shares: 0, reason: step1Reason, step1: step1Reason };
  }

  // 第二步：估值修正
  let multiplier = 1;
  let step2Reason = 'PE在25-32区间，估值修正系数×1.0';
  if (pe < 25) {
    multiplier = 1.2;
    step2Reason = `PE=${pe.toFixed(1)}<25，估值修正×1.2`;
  } else if (pe > 35) {
    multiplier = 0.5;
    step2Reason = `PE=${pe.toFixed(1)}>35，估值修正×0.5`;
  } else if (pe > 32) {
    multiplier = 0.8;
    step2Reason = `PE=${pe.toFixed(1)}在32-35，估值修正×0.8`;
  }

  let adjustedShares = Math.round(baseShares * multiplier * 10) / 10;

  // 第三步：事件降档
  let eventDowngrade = false;
  let eventReason = '无事件降档';
  let skipToday = false;

  // 检查一级事件前1日
  const upcomingEvents = getUpcomingEvents(5);
  const tomorrow = new Date(data.nyTime);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const majorEventTomorrow = upcomingEvents.find(e => {
    const eventDate = new Date(e.date);
    return eventDate.toDateString() === tomorrow.toDateString() && e.level === '一级';
  });
  if (majorEventTomorrow) {
    eventDowngrade = true;
    eventReason = `明日${majorEventTomorrow.name}，降一档`;
  }

  // VIX>30且周跌>5%
  if (vix > 30 && weeklyChange < -5) {
    eventDowngrade = true;
    eventReason = `VIX=${vix.toFixed(1)}>30且周跌${weeklyChange.toFixed(1)}%，降一档`;
  }

  // 黑天鹅
  if (change < -7) {
    skipToday = true;
    eventReason = `单日跌${change.toFixed(2)}%>7%，黑天鹅跳过`;
  }

  // 年末季末
  if (isYearEndQuarterEnd(data.nyTime)) {
    eventDowngrade = true;
    eventReason = '年末/季末最后2个交易日，降一档';
  }

  if (skipToday) {
    return {
      shouldAdd: false,
      shares: 0,
      reason: eventReason,
      step1: step1Reason,
      step2: step2Reason,
      step3: eventReason,
      extremeDrop: true,
    };
  }

  if (eventDowngrade) {
    if (adjustedShares >= 1) adjustedShares = 0.5;
    else if (adjustedShares >= 0.5) adjustedShares = 0;
  }

  // 周度累计加仓上限检查（本周周一到当前日已加仓总额 >= 1份则当日不再加仓）
  if (adjustedShares > 0) {
    const history = getInvestHistory();
    const today = new Date(data.nyTime);
    const dayOfWeek = today.getDay();
    // 计算本周一的日期
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
    const monday = new Date(today);
    monday.setDate(today.getDate() + mondayOffset);
    monday.setHours(0, 0, 0, 0);
    const mondayStr = formatDateStr(monday);
    // 统计本周额外加仓总额（排除周四定投），转换为份数
    const weeklyAddTotal = history
      .filter(h => h.date >= mondayStr && h.type === '额外加仓')
      .reduce((sum, h) => sum + h.amount, 0) / 1000;
    if (weeklyAddTotal >= 1) {
      return {
        shouldAdd: false,
        shares: 0,
        reason: step1Reason + '；' + step2Reason + '；本周已加仓' + formatAmount(weeklyAddTotal) + '元，达周度上限' + formatAmount(1) + '元',
        step1: step1Reason,
        step2: step2Reason,
        step3: '周度加仓上限已满（本周已加仓' + formatAmount(weeklyAddTotal) + '元）',
      };
    }
  }

  // 连续加仓检测
  if (adjustedShares > 0) {
    consecutiveAddDays++;
    if (consecutiveAddDays >= 3) {
      // 连续3日加仓，强制降一档：1→0.5, 0.5→0
      let downgradedShares = adjustedShares;
      if (adjustedShares >= 1) downgradedShares = 0.5;
      else if (adjustedShares >= 0.5) downgradedShares = 0;
      return {
        shouldAdd: downgradedShares > 0,
        shares: downgradedShares,
        reason: step1Reason + '；' + step2Reason + '；' + eventReason,
        step1: step1Reason,
        step2: step2Reason,
        step3: eventReason,
        warning: `连续${consecutiveAddDays}日加仓，强制降一档（${formatAmount(adjustedShares)}→${formatAmount(downgradedShares)}元）`,
      };
    }
  } else {
    consecutiveAddDays = 0;
  }

  return {
    shouldAdd: adjustedShares > 0,
    shares: adjustedShares,
    reason: step1Reason + '；' + step2Reason + '；' + eventReason,
    step1: step1Reason,
    step2: step2Reason,
    step3: eventReason,
  };
}

// ===== 事件日历 =====
function getUpcomingEvents(days = 5) {
  const events = [];
  const today = new Date(getNYTime());

  // 已知的定期经济事件（2026年）
  // FOMC利率决议（通常为周三）
  const fomcDates = [
    '2026-01-28', '2026-03-18', '2026-05-06', '2026-06-17',
    '2026-07-29', '2026-09-16', '2026-11-04', '2026-12-16',
  ];

  // CPI发布日（通常为月中周二）
  const cpiDates = [
    '2026-01-15', '2026-02-12', '2026-03-11', '2026-04-14',
    '2026-05-13', '2026-06-11', '2026-07-15', '2026-08-12',
    '2026-09-10', '2026-10-14', '2026-11-11', '2026-12-10',
  ];

  // 非农就业数据（通常为每月第一个周五）
  const nonFarmDates = [
    '2026-01-09', '2026-02-06', '2026-03-06', '2026-04-03',
    '2026-05-01', '2026-06-05', '2026-07-03', '2026-08-07',
    '2026-09-04', '2026-10-02', '2026-11-06', '2026-12-04',
  ];

  // GDP发布日（每季度末后一个月）
  const gdpDates = [
    '2026-01-29', '2026-04-29', '2026-07-29', '2026-10-29',
  ];

  // 零售销售（通常月中）
  const retailDates = [
    '2026-01-16', '2026-02-18', '2026-03-17', '2026-04-16',
    '2026-05-15', '2026-06-16', '2026-07-16', '2026-08-14',
    '2026-09-16', '2026-10-16', '2026-11-17', '2026-12-16',
  ];

  // PPI发布日（通常为月中，CPI次日）
  const ppiDates = [
    '2026-01-16', '2026-02-13', '2026-03-12', '2026-04-15',
    '2026-05-14', '2026-06-12', '2026-07-16', '2026-08-13',
    '2026-09-11', '2026-10-15', '2026-11-12', '2026-12-11',
  ];

  // 消费者信心指数（密歇根大学，通常月中）
  const consumerConfidenceDates = [
    '2026-01-16', '2026-02-13', '2026-03-13', '2026-04-17',
    '2026-05-15', '2026-06-12', '2026-07-17', '2026-08-14',
    '2026-09-18', '2026-10-16', '2026-11-13', '2026-12-18',
  ];

  for (let i = 0; i < days; i++) {
    const date = new Date(today);
    date.setDate(date.getDate() + i);
    const dateStr = formatDateStr(date);

    fomcDates.forEach(d => {
      if (d === dateStr) events.push({ date: d, name: 'FOMC利率决议', impact: 'neutral', level: '一级', impactRating: '高' });
    });
    cpiDates.forEach(d => {
      if (d === dateStr) events.push({ date: d, name: 'CPI通胀数据', impact: 'neutral', level: '一级', impactRating: '高' });
    });
    nonFarmDates.forEach(d => {
      if (d === dateStr) events.push({ date: d, name: '非农就业数据', impact: 'neutral', level: '一级', impactRating: '高' });
    });
    gdpDates.forEach(d => {
      if (d === dateStr) events.push({ date: d, name: 'GDP数据', impact: 'neutral', level: '二级', impactRating: '中' });
    });
    retailDates.forEach(d => {
      if (d === dateStr) events.push({ date: d, name: '零售销售', impact: 'neutral', level: '二级', impactRating: '中' });
    });
    ppiDates.forEach(d => {
      if (d === dateStr) events.push({ date: d, name: 'PPI生产者物价', impact: 'neutral', level: '二级', impactRating: '中' });
    });
    consumerConfidenceDates.forEach(d => {
      if (d === dateStr) events.push({ date: d, name: '消费者信心指数', impact: 'neutral', level: '三级', impactRating: '低' });
    });
  }

  // 按日期排序
  events.sort((a, b) => new Date(a.date) - new Date(b.date));

  // 如果没有事件
  if (events.length === 0) {
    return [{ date: formatDateStr(new Date(today)), name: '近5日数据真空期', impact: 'neutral', level: '无', impactRating: '低' }];
  }

  return events;
}

function isYearEndQuarterEnd(date) {
  const month = date.getMonth(); // 0-indexed
  const day = date.getDate();
  // 12月末最后2个交易日、3/6/9月末最后2个交易日
  const lastDay = new Date(date.getFullYear(), month + 1, 0).getDate();
  return (month === 11 && day >= lastDay - 2) ||
         ([2, 5, 8].includes(month) && day >= lastDay - 2);
}

// ===== 趋势判断 =====
function analyzeTrend(data) {
  const price = data.ndx.price;
  const ma20 = data.ndx.ma20;
  const drawdown = data.ndx.drawdown;
  const pe = data.pe;

  let trend = '';
  let trendEmoji = '';
  let advice = '';

  if (price > ma20 * 1.05) {
    trend = '强势上涨';
    trendEmoji = '🚀';
    advice = '趋势向上，按正常档位执行定投。不追高加仓。';
  } else if (price > ma20) {
    trend = '温和上涨';
    trendEmoji = '📈';
    advice = '价格在均线上方运行，定投按标准执行。';
  } else if (price > ma20 * 0.95) {
    trend = '横盘震荡';
    trendEmoji = '↔️';
    advice = '价格在均线附近震荡，坚持定投收集筹码。';
  } else if (price > ma20 * 0.9) {
    trend = '回调修正';
    trendEmoji = '📉';
    advice = '价格低于均线，逢低加仓机会。关注PE档位。';
  } else {
    trend = '明显下跌';
    trendEmoji = '⬇️';
    advice = '价格大幅低于均线，严格执行加仓规则，不恐慌卖出。';
  }

  return { trend, trendEmoji, advice, drawdown, ma20 };
}

// ===== 数据说服 =====
function generateDataPersuasion(data) {
  const pe = data.pe;
  const assetRatio = userSettings.totalAssets;
  const baseAmount = userSettings.baseAmount || 1000;
  const weeklyShares = data.peGrade.shares || (data.peGrade.amount ? data.peGrade.amount / 1000 : 1);
  const weeklyRatio = (baseAmount / 1000 * weeklyShares * 0.15 * assetRatio).toFixed(2);

  // 历史定投收益概率（基于PE起点）
  let prob12m = '70%';
  let maxDrawdownPct = '15%';
  let startPE = pe;

  if (pe < 25) {
    prob12m = '85%';
    maxDrawdownPct = '10%';
  } else if (pe <= 28) {
    prob12m = '78%';
    maxDrawdownPct = '12%';
  } else if (pe <= 32) {
    prob12m = '70%';
    maxDrawdownPct = '15%';
  } else if (pe <= 35) {
    prob12m = '60%';
    maxDrawdownPct = '20%';
  } else {
    prob12m = '50%';
    maxDrawdownPct = '25%';
  }

  // 从定投记录计算累计份数
  const totalInvestedAmount = getHistoryTotalInvested();
  const totalShares = totalInvestedAmount / 1000;
  // 累计投入占总资产比例（用系数简化）
  const investedRatio = totalShares > 0
    ? (baseAmount / 1000 * 0.15 * totalShares * assetRatio).toFixed(2)
    : '0.00';

  return {
    weeklyRatio,
    prob12m,
    maxDrawdownPct,
    lossRatio: maxDrawdownPct,
    startPE: pe.toFixed(1),
    totalShares,
    investedRatio,
  };
}

// 从定投记录计算累计投入
function getHistoryTotalInvested() {
  const history = getInvestHistory();
  return history.reduce((sum, h) => sum + h.amount, 0);
}

// ===== 多维度分析系统 =====

function generateMultiDimensionAnalysis(data) {
  const pe = data.pe;
  const vix = data.vix || 0;
  const price = data.ndx.price;
  const ma20 = data.ndx.ma20;
  const drawdown = data.ndx.drawdown;
  const change = data.ndx.change;
  const weeklyChange = data.ndx.weeklyChange;
  const treasury10y = data.treasury10y || 0;

  // --- 基本面分析 ---
  const peMid = 26.5;
  const peDiffPct = ((pe - peMid) / peMid * 100);
  const pePercentile = calculatePEPercentile(pe);
  let fundamentalColor = 'green';
  let fundamentalConclusion = '估值合理偏低，具备安全边际';
  if (pe > 40) {
    fundamentalColor = 'red';
    fundamentalConclusion = '估值偏高，不具备安全边际';
  } else if (pe > 35) {
    fundamentalColor = 'orange';
    fundamentalConclusion = '估值偏高，安全边际不足';
  } else if (pe > 32) {
    fundamentalColor = 'yellow';
    fundamentalConclusion = '估值偏高，安全边际有限';
  } else if (pe > 28) {
    fundamentalColor = 'blue';
    fundamentalConclusion = '估值合理，可正常定投';
  }

  const fundamental = {
    title: '基本面分析',
    subtitle: '价值投资者视角',
    color: fundamentalColor,
    icon: '📊',
    items: [
      `PE当前值 ${pe.toFixed(1)} 倍 vs 历史中枢 25-28 倍`,
      `当前PE位于历史 ${pePercentile.toFixed(0)}% 分位`,
      `2000年泡沫峰值约75倍，2021年高点约38倍`,
    ],
    conclusion: fundamentalConclusion,
    consensus: pe > 35 ? 'pause' : pe > 28 ? 'neutral' : 'buy',
  };

  // --- 情绪面分析 ---
  let sentimentColor = 'green';
  let sentimentConclusion = '市场情绪平稳，适合入场';
  let sentimentStatus = '正常';
  if (vix > 30) {
    sentimentColor = 'red';
    sentimentConclusion = '市场恐慌情绪浓厚，谨慎入场';
    sentimentStatus = '高恐慌';
  } else if (vix > 25) {
    sentimentColor = 'orange';
    sentimentConclusion = '市场情绪偏恐慌，观望为主';
    sentimentStatus = '偏高';
  } else if (vix > 20) {
    sentimentColor = 'yellow';
    sentimentConclusion = '市场情绪偏乐观，保持警惕';
    sentimentStatus = '偏乐观';
  } else if (change > 2 || weeklyChange > 3) {
    sentimentColor = 'yellow';
    sentimentConclusion = '市场情绪偏乐观，不适合追高';
    sentimentStatus = '偏乐观';
  } else if (change < -3 || weeklyChange < -5) {
    sentimentColor = 'green';
    sentimentConclusion = '市场情绪偏悲观，定投良机';
    sentimentStatus = '偏悲观';
  }

  const sentiment = {
    title: '情绪面分析',
    subtitle: '行为金融学视角',
    color: sentimentColor,
    icon: '🧠',
    items: [
      `VIX当前值 ${vix.toFixed(1)}（${sentimentStatus}）`,
      `前日涨跌 ${change >= 0 ? '+' : ''}${change.toFixed(2)}%，周涨跌 ${weeklyChange >= 0 ? '+' : ''}${weeklyChange.toFixed(2)}%`,
      `散户情绪指标：${vix < 15 && change > 1 ? '贪婪' : vix > 25 ? '恐惧' : '中性'}`,
    ],
    conclusion: sentimentConclusion,
    consensus: vix > 30 ? 'pause' : vix > 25 ? 'neutral' : 'buy',
  };

  // --- 技术面分析 ---
  const ma20Distance = ((price - ma20) / ma20 * 100);
  let techColor = 'blue';
  let techConclusion = '技术面中性';
  let techStatus = '中性';
  if (ma20Distance > 5) {
    techColor = 'orange';
    techConclusion = '技术面显示超买';
    techStatus = '超买';
  } else if (ma20Distance > 2) {
    techColor = 'yellow';
    techConclusion = '技术面偏强';
    techStatus = '偏强';
  } else if (ma20Distance < -5) {
    techColor = 'green';
    techConclusion = '技术面显示超卖';
    techStatus = '超卖';
  } else if (ma20Distance < -2) {
    techColor = 'blue';
    techConclusion = '技术面偏弱';
    techStatus = '偏弱';
  }

  const recentCloses = data.ndx.recentCloses;
  const ma60 = recentCloses.length >= 60
    ? recentCloses.slice(-60).reduce((a, b) => a + b, 0) / 60
    : recentCloses.reduce((a, b) => a + b, 0) / recentCloses.length;
  const ma60Distance = ((price - ma60) / ma60 * 100);

  const tech = {
    title: '技术面分析',
    subtitle: '量化交易视角',
    color: techColor,
    icon: '📈',
    items: [
      `价格 vs 20日均线：${ma20Distance >= 0 ? '+' : ''}${ma20Distance.toFixed(1)}%（${techStatus}）`,
      `60日回撤幅度：${drawdown.toFixed(1)}%`,
      `近期趋势：${data.ndx.ma20Direction === 'up' ? '上涨' : '下跌'}（20日均线方向）`,
    ],
    conclusion: techConclusion,
    consensus: ma20Distance > 5 ? 'pause' : ma20Distance < -5 ? 'buy' : 'neutral',
  };

  // --- 消息面分析 ---
  const upcomingEvents = getUpcomingEvents(5);
  const majorEvents = upcomingEvents.filter(e => e.level === '一级');
  const hasMajorEventSoon = majorEvents.length > 0;
  const nextEvent = upcomingEvents[0];
  let nextEventText = '近期无重大事件';
  if (nextEvent && nextEvent.name !== '近5日数据真空期') {
    const daysUntil = Math.ceil((new Date(nextEvent.date) - new Date(getNYTime())) / (1000 * 60 * 60 * 24));
    nextEventText = `${nextEvent.name}（${daysUntil <= 0 ? '今日' : daysUntil + '天后'}）`;
  }

  let macroColor = 'blue';
  let macroConclusion = '宏观环境中性';
  if (treasury10y > 5.0) {
    macroColor = 'red';
    macroConclusion = '资金成本高企，宏观环境不支持';
  } else if (treasury10y > 4.5) {
    macroColor = 'orange';
    macroConclusion = '资金成本偏高，宏观环境偏紧';
  } else if (treasury10y < 3.5) {
    macroColor = 'green';
    macroConclusion = '资金成本较低，宏观环境支持';
  }

  if (hasMajorEventSoon) {
    macroColor = macroColor === 'green' ? 'yellow' : 'orange';
    macroConclusion += '，但近期有重要事件需关注';
  }

  const macro = {
    title: '消息面分析',
    subtitle: '宏观策略视角',
    color: macroColor,
    icon: '🌍',
    items: [
      `近期重要事件：${nextEventText}`,
      `事件对市场影响：${hasMajorEventSoon ? '可能引发短期波动' : '有限'}`,
      `10年期美债收益率：${treasury10y.toFixed(2)}%（资金成本）`,
    ],
    conclusion: macroConclusion,
    consensus: treasury10y > 5.0 || hasMajorEventSoon ? 'pause' : treasury10y > 4.5 ? 'neutral' : 'buy',
  };

  // --- 综合决策 ---
  const perspectives = [fundamental, sentiment, tech, macro];
  const pauseCount = perspectives.filter(p => p.consensus === 'pause').length;
  const buyCount = perspectives.filter(p => p.consensus === 'buy').length;
  const neutralCount = perspectives.filter(p => p.consensus === 'neutral').length;

  let overallConsensus = 'neutral';
  let overallAction = '维持当前档位';
  if (pauseCount >= 3) {
    overallConsensus = 'pause';
    overallAction = '建议暂停或最低档定投';
  } else if (pauseCount >= 2) {
    overallConsensus = 'caution';
    overallAction = '建议谨慎，降低档位';
  } else if (buyCount >= 3) {
    overallConsensus = 'buy';
    overallAction = '建议积极定投';
  } else if (buyCount >= 2) {
    overallConsensus = 'favorable';
    overallAction = '建议正常或加码定投';
  }

  // 恢复定投触发条件
  const resumeConditions = [
    { label: 'PE < 35', check: pe < 35, current: `当前 ${pe.toFixed(1)}` },
    { label: 'VIX < 20', check: vix < 20, current: `当前 ${vix.toFixed(1)}` },
    { label: '无重大事件', check: !hasMajorEventSoon, current: hasMajorEventSoon ? '有' : '无' },
  ];
  const resumeMet = resumeConditions.filter(c => c.check).length;
  const resumeTotal = resumeConditions.length;

  return {
    perspectives: [fundamental, sentiment, tech, macro],
    consensus: {
      pauseCount,
      buyCount,
      neutralCount,
      total: perspectives.length,
      overallConsensus,
      overallAction,
    },
    resumeConditions,
    resumeMet,
    resumeTotal,
    canResume: resumeMet === resumeTotal,
  };
}

// ===== 综合评分计算 =====
function calculateCompositeScore(data, analysis) {
  let score = 50;

  // PE评分（最高25分）
  if (data.pe <= 25) score += 25;
  else if (data.pe <= 28) score += 15;
  else if (data.pe <= 32) score += 5;
  else if (data.pe <= 35) score -= 10;
  else if (data.pe <= 40) score -= 20;
  else score -= 25;

  // VIX评分（最高20分）
  if (data.vix > 30) score += 20;
  else if (data.vix > 25) score += 10;
  else if (data.vix > 20) score += 0;
  else if (data.vix > 15) score -= 5;
  else score -= 10;

  // 技术面评分（最高20分）
  const ma20Distance = ((data.ndx.price - data.ndx.ma20) / data.ndx.ma20 * 100);
  if (ma20Distance < -5) score += 20;
  else if (ma20Distance < -2) score += 10;
  else if (ma20Distance < 2) score += 0;
  else if (ma20Distance < 5) score -= 10;
  else score -= 20;

  // 宏观评分（最高15分）
  if (data.treasury10y < 3.5) score += 15;
  else if (data.treasury10y < 4.0) score += 5;
  else if (data.treasury10y < 4.5) score -= 5;
  else if (data.treasury10y < 5.0) score -= 10;
  else score -= 15;

  // 事件评分（最高20分）
  const upcomingEvents = getUpcomingEvents(5);
  const hasMajorEvent = upcomingEvents.some(e => e.level === '一级');
  if (!hasMajorEvent) score += 20;
  else score -= 10;

  return Math.max(0, Math.min(100, score));
}

// ===== UI渲染层 =====

function renderTodayTab(data) {
  const tab = document.getElementById('tab-today');
  const pe = data.pe;

  // 兼容旧缓存数据：如果peGrade只有amount没有shares，重新计算
  let grade = data.peGrade;
  if (grade && !grade.shares && grade.amount) {
    grade = getPEGrade(pe);
  }

  const addResult = calculateAdditionalBuy(data);
  const trend = analyzeTrend(data);
  const persuasion = generateDataPersuasion(data);
  const events = getUpcomingEvents(5);
  const analysis = generateMultiDimensionAnalysis(data);
  const compositeScore = calculateCompositeScore(data, analysis);

  // PE仪表盘百分比
  const pePercent = Math.min(100, Math.max(0, ((pe - 15) / 35) * 100));

  // PE仪表盘颜色
  let gaugeColor = 'var(--accent-green)';
  if (pe > 28) gaugeColor = 'var(--accent-blue)';
  if (pe > 32) gaugeColor = 'var(--accent-yellow)';
  if (pe > 35) gaugeColor = 'var(--accent-orange)';
  if (pe > 40) gaugeColor = 'var(--accent-red)';

  const changeClass = data.ndx.change >= 0 ? 'green' : 'red';
  const changeSign = data.ndx.change >= 0 ? '+' : '';

  // 事件降档标记
  const eventDowngrade = addResult.step3 && addResult.step3 !== '无事件降档';

  // 连续加仓警告
  const consecutiveWarning = addResult.warning || '';

  // 综合评分颜色
  let scoreColor = 'var(--accent-green)';
  let scoreLabel = '积极定投';
  if (compositeScore < 30) {
    scoreColor = 'var(--accent-red)';
    scoreLabel = '建议暂停';
  } else if (compositeScore < 50) {
    scoreColor = 'var(--accent-orange)';
    scoreLabel = '谨慎定投';
  } else if (compositeScore < 70) {
    scoreColor = 'var(--accent-yellow)';
    scoreLabel = '中性观望';
  }

  // 非交易日提示
  const nonTradingNote = !data.isTradingDay
    ? `<div class="alert-banner info">📅 今日非交易日，${data.frequency === "daily" ? "下次操作窗口为明日开盘" : `下次操作窗口为周四（${data.daysToDCA}天后）`}</div>`
    : '';

  // 周四提示
  const thursdayNote = data.isThursday
    ? `<div class="alert-banner info">📌 ${data.frequency === "daily" ? "今日为交易日，执行每日定投" : "今天是周四，执行定投日。全天禁止加仓"}</div>`
    : '';

  // 极端超跌警告
  const extremeWarning = addResult.extremeDrop
    ? `<div class="alert-banner danger">🚨 极端超跌！单日跌幅超7%，今日跳过加仓</div>`
    : '';

  // 连续加仓警告
  const consecutiveAlert = consecutiveWarning
    ? `<div class="alert-banner warning">⚠️ ${consecutiveWarning}</div>`
    : '';

  // 四维度分析卡片HTML
  const perspectiveCardsHTML = analysis.perspectives.map(p => {
    const colorMap = {
      green: { border: 'var(--accent-green)', bg: 'rgba(34,197,94,0.08)', text: 'var(--accent-green)' },
      red: { border: 'var(--accent-red)', bg: 'rgba(239,68,68,0.08)', text: 'var(--accent-red)' },
      yellow: { border: 'var(--accent-yellow)', bg: 'rgba(234,179,8,0.08)', text: 'var(--accent-yellow)' },
      orange: { border: 'var(--accent-orange)', bg: 'rgba(249,115,22,0.08)', text: 'var(--accent-orange)' },
      blue: { border: 'var(--accent-blue)', bg: 'rgba(59,130,246,0.08)', text: 'var(--accent-blue)' },
    };
    const c = colorMap[p.color] || colorMap.blue;
    return `
      <div style="background:${c.bg};border:1px solid ${c.border};border-radius:10px;padding:12px;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
          <span style="font-size:16px;">${p.icon}</span>
          <div>
            <div style="font-size:13px;font-weight:700;color:var(--text-primary);">${p.title}</div>
            <div style="font-size:10px;color:var(--text-muted);">${p.subtitle}</div>
          </div>
        </div>
        <div style="font-size:11px;color:var(--text-secondary);line-height:1.7;margin-bottom:8px;">
          ${p.items.map(item => `<div>• ${item}</div>`).join('')}
        </div>
        <div style="font-size:12px;font-weight:700;color:${c.text};padding:6px 8px;background:rgba(0,0,0,0.15);border-radius:6px;">
          结论：${p.conclusion}
        </div>
      </div>
    `;
  }).join('');

  // 恢复定投条件进度HTML
  const resumeProgressHTML = analysis.resumeConditions.map(c => {
    const metColor = c.check ? 'var(--accent-green)' : 'var(--accent-red)';
    const metIcon = c.check ? '✅' : '⏳';
    return `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
        <span style="font-size:12px;color:var(--text-secondary);">${metIcon} ${c.label}</span>
        <span style="font-size:12px;color:${metColor};font-weight:600;">${c.current}</span>
      </div>
    `;
  }).join('');

  const resumeProgressPercent = (analysis.resumeMet / analysis.resumeTotal * 100);
  const resumeStatusText = analysis.canResume
    ? '<span style="color:var(--accent-green);font-weight:700;">✅ 条件已满足，可恢复定投</span>'
    : `<span style="color:var(--accent-yellow);">⏳ 已满足 ${analysis.resumeMet}/${analysis.resumeTotal} 个条件</span>`;

  // 事件时间线HTML（增强版）
  const eventTimelineHTML = events.map(e => {
    const impactClass = e.impact === 'bullish' ? 'bullish' : e.impact === 'bearish' ? 'bearish' : 'neutral';
    const impactText = e.impact === 'bullish' ? '利好' : e.impact === 'bearish' ? '利空' : '中性';
    const dateObj = new Date(e.date + 'T12:00:00');
    const dateText = `${dateObj.getMonth() + 1}月${dateObj.getDate()}日`;
    const daysUntil = Math.ceil((dateObj - new Date(getNYTime())) / (1000 * 60 * 60 * 24));
    const countdownText = daysUntil <= 0 ? '今日' : `还有${daysUntil}天`;
    const ratingColor = e.impactRating === '高' ? 'var(--accent-red)' : e.impactRating === '中' ? 'var(--accent-yellow)' : 'var(--text-muted)';
    return `
      <div class="event-item">
        <span class="event-date">${dateText}</span>
        <div style="flex:1">
          <div class="event-name">${e.name}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${countdownText}</div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;">
          <span class="event-impact ${impactClass}">${impactText}</span>
          <span style="font-size:10px;color:${ratingColor};font-weight:600;">${e.impactRating}影响</span>
        </div>
      </div>
    `;
  }).join('');

  // 操作指令大字显示
  const totalShares = grade.shares + (addResult.shouldAdd ? addResult.shares : 0);
  const actionText = grade.shares === 0 ? '暂停定投' : `定投 ${formatAmount(totalShares)}元`;
  const actionClass = grade.class;

  tab.innerHTML = `
    ${nonTradingNote}
    ${thursdayNote}
    ${extremeWarning}
    ${consecutiveAlert}

    <!-- 操作指令（首屏置顶） -->
    <div class="card action-card ${actionClass}">
      <div class="card-title"><span class="emoji">⚡</span>操作指令</div>
      <div class="action-amount ${grade.color}" style="font-size:${actionText.length > 8 ? "28px" : "32px"};">${actionText}</div>
      <div style="text-align:center;font-size:12px;color:var(--text-muted);margin-bottom:12px;">
        PE=${pe.toFixed(1)}倍 → ${grade.level}档
        ${addResult.shouldAdd ? ` | 额外加仓 ${formatAmount(addResult.shares)}元` : ''}
      </div>

      <!-- 综合评分（内嵌到操作卡片） -->
      <div style="text-align:center;padding:12px 0;border-top:1px solid rgba(255,255,255,0.08);border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:12px;">
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">投资仪表盘综合评分</div>
        <div style="font-size:36px;font-weight:800;color:${scoreColor};line-height:1;">${compositeScore}</div>
        <div style="font-size:13px;color:${scoreColor};font-weight:600;">${scoreLabel}</div>
        <div style="width:100%;height:5px;background:rgba(0,0,0,0.3);border-radius:3px;margin-top:8px;overflow:hidden;">
          <div style="width:${compositeScore}%;height:100%;background:${scoreColor};border-radius:3px;transition:width 0.8s ease;"></div>
        </div>
      </div>

      <!-- 综合决策 -->
      <div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:12px;">
        <div style="font-size:12px;font-weight:700;color:var(--text-primary);margin-bottom:6px;">
          🎯 投资团队共识：${analysis.consensus.pauseCount}/${analysis.consensus.total} 视角建议暂停
        </div>
        <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;">
          ${analysis.consensus.overallAction}
        </div>
        ${!analysis.canResume ? `
          <div style="font-size:11px;color:var(--accent-yellow);margin-top:6px;padding:6px 8px;background:rgba(234,179,8,0.1);border-radius:6px;">
            📌 恢复定投触发条件：PE < 35 且 VIX < 20 且 无重大事件
          </div>
        ` : ''}
      </div>
    </div>

    <!-- 四维度分析卡片网格 -->
    <div class="card">
      <div class="card-title"><span class="emoji">🔍</span>投资团队多视角分析</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        ${perspectiveCardsHTML}
      </div>
    </div>

    <!-- 恢复定投条件进度 -->
    <div class="card">
      <div class="card-title"><span class="emoji">📌</span>恢复定投触发条件</div>
      ${resumeProgressHTML}
      <div style="margin-top:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span style="font-size:12px;color:var(--text-secondary);">总体进度</span>
          <span style="font-size:12px;font-weight:700;">${resumeStatusText}</span>
        </div>
        <div style="width:100%;height:8px;background:rgba(0,0,0,0.3);border-radius:4px;overflow:hidden;">
          <div style="width:${resumeProgressPercent}%;height:100%;background:${analysis.canResume ? 'var(--accent-green)' : 'var(--accent-yellow)'};border-radius:4px;transition:width 0.8s ease;"></div>
        </div>
      </div>
    </div>

    <!-- 近期事件时间线 -->
    <div class="card">
      <div class="card-title"><span class="emoji">📅</span>近期事件时间线</div>
      ${eventTimelineHTML}
    </div>

    <!-- 环境快照 -->
    <div class="card">
      <div class="card-title"><span class="emoji">📊</span>环境快照</div>
      <div class="data-grid">
        <div class="data-item">
          <div class="data-label">纳指收盘</div>
          <div class="data-value">${data.ndx.price?.toFixed(0) || '--'}</div>
          <div class="data-sub ${changeClass}">${changeSign}${data.ndx.change?.toFixed(2)}%</div>
        </div>
        <div class="data-item">
          <div class="data-label">PE（市盈率）</div>
          <div class="data-value ${grade.color}">${pe.toFixed(1)}倍</div>
          <div class="data-sub">${grade.level}档</div>
        </div>
        <div class="data-item">
          <div class="data-label">VIX恐慌指数</div>
          <div class="data-value ${data.vix > 25 ? 'orange' : data.vix > 20 ? 'yellow' : 'green'}">${data.vix?.toFixed(1) || '--'}</div>
          <div class="data-sub">${data.vix > 30 ? '高恐慌' : data.vix > 20 ? '偏高' : '正常'}</div>
        </div>
        <div class="data-item">
          <div class="data-label">10Y美债收益率</div>
          <div class="data-value">${data.treasury10y?.toFixed(2) || '--'}%</div>
          <div class="data-sub">股债比: ${data.equityBondRatio}</div>
        </div>
        <div class="data-item">
          <div class="data-label">${data.frequency === "daily" ? "距下次定投" : "距周四定投"}</div>
          <div class="data-value">${data.frequency === "daily" ? (data.isTradingDay ? "今天" : "明天") : data.daysToDCA + "天"}</div>
          <div class="data-sub">${data.frequency === 'daily' ? (data.isTradingDay ? '今日定投日' : '非交易日') : (data.isThursday ? '今天就是周四！' : (data.isTradingDay ? '交易日' : '非交易日'))}</div>
        </div>
        <div class="data-item">
          <div class="data-label">20日均线</div>
          <div class="data-value">${data.ndx.ma20?.toFixed(0) || '--'}</div>
          <div class="data-sub ${data.ndx.ma20Direction === 'up' ? 'green' : 'red'}">${data.ndx.ma20Direction === 'up' ? '↗ 向上' : '↘ 向下'}</div>
        </div>
      </div>

      <!-- PE仪表盘 -->
      <div class="pe-gauge">
        <div class="pe-gauge-fill" style="width:${pePercent}%;background:${gaugeColor}"></div>
        <div class="pe-gauge-marker" style="left:${pePercent}%"></div>
      </div>
      <div class="pe-gauge-labels">
        <span>15</span><span>25</span><span>28</span><span>32</span><span>35</span><span>40</span><span>50</span>
      </div>

      <!-- 迷你走势图 -->
      ${generateMiniChart(data.ndx.recentCloses)}
    </div>

    <!-- 心理锚点 -->
    <div class="card">
      <div class="card-title"><span class="emoji">🧠</span>心理锚点</div>
      <div style="font-size:14px;line-height:1.8;color:var(--text-secondary)">
        今日PE=<span class="${grade.color}" style="font-weight:700">${pe.toFixed(1)}</span>倍（<span class="${grade.color}">${grade.level}</span>档）。
        纳指长期PE中枢约25-28倍。
        你每周定投占总资产仅<span class="${grade.color}" style="font-weight:700">${persuasion.weeklyRatio}%</span>，
        即便全亏也不影响生活。
        ${persuasion.totalShares > 0 ? `你当前定投占总资产的<span class="${grade.color}" style="font-weight:700">${persuasion.investedRatio}%</span>，累计${formatAmount(persuasion.totalShares)}元。` : ''}
        <strong style="color:var(--text-primary)">浮亏是假的，份额是真的。</strong>
      </div>
    </div>

    <!-- 趋势判断 -->
    <div class="card">
      <div class="card-title"><span class="emoji">📈</span>趋势判断</div>
      <div class="trend-indicator">
        <span class="trend-arrow">${trend.trendEmoji}</span>
        <div>
          <div class="trend-text">纳指处于 <span class="${data.ndx.ma20Direction === 'up' ? 'green' : 'red'}">${trend.trend}</span> 趋势</div>
          <div class="trend-detail">20日均线${data.ndx.ma20Direction === 'up' ? '↗向上' : '↘向下'}，从高点回撤${data.ndx.drawdown.toFixed(1)}%</div>
        </div>
      </div>
      <div style="font-size:12px;color:var(--text-secondary);margin-top:10px;line-height:1.6;">
        ${trend.advice}
      </div>
    </div>

    <!-- 数据说服 -->
    <div class="card quote-card">
      <div class="card-title" style="justify-content:center"><span class="emoji">📊</span>数据说服</div>
      <div class="quote-text">
        你当前定投占总资产的<span class="${grade.color}" style="font-weight:700">${persuasion.investedRatio}%</span>，
        历史上PE从${persuasion.startPE}倍开始定投，持有12个月正收益概率约${persuasion.prob12m}。
        最可能情景下最大浮亏约占总资产${persuasion.lossRatio}%。
      </div>
      <div class="quote-text" style="font-size:14px;margin-top:8px;">
        市场恐惧时坚持买入，是定投策略超额收益的来源。<br>
        <strong>执行它，关掉软件。</strong>
      </div>
    </div>
    ${renderTHSETFPanel(data)}
  `;
}

// ===== 同花顺纳指ETF折溢价面板 =====
function renderTHSETFPanel(data) {
  const ths = data.ths;
  if (!ths || !ths.etfs || ths.etfs.length === 0) {
    return '';
  }

  // 纳指基准价：优先用ths采集的纳指点位，否则用Yahoo的
  const ndxPrice = ths.ndx_index?.price || data.ndx?.price;
  if (!ndxPrice || ndxPrice <= 0) return '';

  // ETF份额面值估算（中国ETF通常按1元面值，但纳指ETF清算时按净值）
  // 纳指ETF通常跟踪Nasdaq-100，1份约等于纳指点位/某个系数
  // 这里用最近一天净值估算折溢价
  let rows = ths.etfs.map(etf => {
    const price = parseFloat(etf.price) || 0;
    const prevClose = parseFloat(etf.prev_close) || price;
    const changePct = etf.change_pct ? parseFloat(etf.change_pct) : 0;
    const changeSign = changePct >= 0 ? '+' : '';
    const changeClass = changePct >= 0 ? 'green' : 'red';

    // 折溢价估算：ETF价格 vs 纳指点位归一化
    // 纳指ETF通常初始净值为1.00，跟踪纳指涨跌
    // 简化模型：估算净值 = 1.00 * (ndxPrice / 基准纳指点位)
    // 取各ETF上市日纳指点位作为基准
    const baseNDX = getETFBaseNDX(etf.code);
    const estNAV = baseNDX > 0 ? (1.0 * ndxPrice / baseNDX) : null;
    const premium = estNAV ? ((price - estNAV) / estNAV * 100) : null;

    let premiumHtml = '';
    if (premium !== null) {
      const pColor = Math.abs(premium) < 0.5 ? 'blue' : (premium > 0 ? 'red' : 'green');
      const pSign = premium >= 0 ? '+' : '';
      premiumHtml = `<span class="${pColor}" style="font-weight:600">${pSign}${premium.toFixed(2)}%</span>`;
    } else {
      premiumHtml = `<span style="color:var(--text-secondary)">--</span>`;
    }

    return `
      <tr>
        <td style="font-size:13px;white-space:nowrap;">${etf.name.replace('纳斯达克ETF', '纳指ETF').replace('纳指ETF', '').replace('100', '') || etf.code.slice(-4)}</td>
        <td style="font-weight:600;">${price.toFixed(3)}</td>
        <td class="${changeClass}" style="font-weight:500;">${changeSign}${changePct.toFixed(2)}%</td>
        <td>${premiumHtml}</td>
      </tr>`;
  }).join('');

  return `
    <div class="card">
      <div class="card-title"><span class="emoji">🏦</span>纳指ETF行情 <span style="font-size:11px;color:var(--text-secondary);margin-left:6px;">(同花顺)</span></div>
      <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-color);color:var(--text-secondary);font-size:11px;">
              <th style="text-align:left;padding:6px 4px;">名称</th>
              <th style="text-align:right;padding:6px 4px;">价格</th>
              <th style="text-align:right;padding:6px 4px;">涨跌</th>
              <th style="text-align:right;padding:6px 4px;">折溢价</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div style="font-size:11px;color:var(--text-secondary);margin-top:8px;line-height:1.5;">
        📌 折溢价 = (ETF市价 - 估算净值) / 估算净值 × 100%。仅供参考，实际以基金公司公告为准。
      </div>
    </div>`;
}

// 各ETF上市日对应纳指点位（用于估算净值基准）
function getETFBaseNDX(code) {
  const baselines = {
    'USHJ513300': 17744,  // 华夏纳斯达克100ETF，上市日2023-01附近纳指约17744
    'USHJ513110': 16534,  // 华泰柏瑞纳指100ETF
    'USHJ513870': 16657,  // 富国纳指100ETF
    'USHJ513390': 18100,  // 博时纳指100ETF
    'USZJ159513': 20007,  // 大成纳斯达克100ETF
    'USZJ159632': 19907,  // 华安纳斯达克ETF
    'USZJ159659': 20020,  // 招商纳斯达克100ETF
    'USZJ159501': 17034,  // 嘉实纳指ETF
  };
  return baselines[code] || 0;
}

function renderShortTermTab(data) {
  const tab = document.getElementById('tab-short');
  const addResult = calculateAdditionalBuy(data);
  const trend = analyzeTrend(data);
  const events = getUpcomingEvents(5);

  // 近5日价格走势
  const recentPrices = data.ndx.recentCloses.slice(-5);
  const priceChange5d = recentPrices.length >= 2
    ? ((recentPrices[recentPrices.length - 1] - recentPrices[0]) / recentPrices[0] * 100)
    : 0;

  // VIX趋势
  const vixTrend = data.vixRecent.length >= 3
    ? (data.vixRecent[data.vixRecent.length - 1] > data.vixRecent[0] ? '上升' : '下降')
    : '稳定';

  tab.innerHTML = `
    <div class="card">
      <div class="card-title"><span class="emoji">🔍</span>短期分析（1-5日）</div>
      <div class="data-grid">
        <div class="data-item">
          <div class="data-label">近5日涨跌</div>
          <div class="data-value ${priceChange5d >= 0 ? 'green' : 'red'}">${priceChange5d >= 0 ? '+' : ''}${priceChange5d.toFixed(2)}%</div>
        </div>
        <div class="data-item">
          <div class="data-label">VIX趋势</div>
          <div class="data-value ${vixTrend === '上升' ? 'orange' : 'green'}">${vixTrend}</div>
          <div class="data-sub">当前${data.vix?.toFixed(1)}</div>
        </div>
        <div class="data-item">
          <div class="data-label">距20日均线</div>
          <div class="data-value ${data.ndx.price > data.ndx.ma20 ? 'green' : 'red'}">
            ${((data.ndx.price - data.ndx.ma20) / data.ndx.ma20 * 100).toFixed(1)}%
          </div>
        </div>
        <div class="data-item">
          <div class="data-label">从高点回撤</div>
          <div class="data-value ${data.ndx.drawdown > 10 ? 'red' : data.ndx.drawdown > 5 ? 'yellow' : 'green'}">
            ${data.ndx.drawdown.toFixed(1)}%
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><span class="emoji">⚡</span>短期操作建议</div>
      <div style="font-size:14px;line-height:1.8;color:var(--text-secondary)">
        ${generateShortTermAdvice(data, addResult, trend)}
      </div>
    </div>

    <div class="card">
      <div class="card-title"><span class="emoji">📅</span>近期事件影响</div>
      ${events.map(e => {
        const dateObj = new Date(e.date + 'T12:00:00');
        const daysUntil = Math.ceil((dateObj - new Date(getNYTime())) / (1000 * 60 * 60 * 24));
        const countdownText = daysUntil <= 0 ? '今日' : `还有${daysUntil}天`;
        const ratingColor = e.impactRating === '高' ? 'var(--accent-red)' : e.impactRating === '中' ? 'var(--accent-yellow)' : 'var(--text-muted)';
        return `
          <div class="event-item">
            <span class="event-date">${dateObj.getMonth() + 1}/${dateObj.getDate()}</span>
            <div style="flex:1">
              <div class="event-name">${e.name}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${countdownText}</div>
            </div>
            <span style="font-size:10px;color:${ratingColor};font-weight:600;">${e.impactRating}影响</span>
          </div>
        `;
      }).join('')}
    </div>

    <div class="card quote-card">
      <div class="quote-text">
        ${data.ndx.drawdown > 10
          ? '📉 短期回调较大，但定投策略不怕下跌。下跌正是收集廉价份额的时机。保持纪律，按规则执行。'
          : data.ndx.change > 2
            ? '📈 短期涨幅较大，不追高。按正常档位定投即可，额外加仓条件未满足。'
            : '↔️ 短期市场平稳运行，坚持每周定投纪律。不因涨跌情绪化操作。'
        }
      </div>
    </div>
  `;
}

function renderMidTermTab(data) {
  const tab = document.getElementById('tab-mid');

  // 近30日数据
  const closes = data.ndx.recentCloses;
  const high30 = Math.max(...closes);
  const low30 = Math.min(...closes);
  const current = data.ndx.price;
  const midChange = closes.length >= 2
    ? ((current - closes[0]) / closes[0] * 100)
    : 0;

  // 波动率（近30日）
  const returns = [];
  for (let i = 1; i < closes.length; i++) {
    returns.push((closes[i] - closes[i - 1]) / closes[i - 1]);
  }
  const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
  const volatility = Math.sqrt(returns.reduce((sum, r) => sum + (r - avgReturn) ** 2, 0) / returns.length) * Math.sqrt(252) * 100;

  // PE趋势
  const peHistory = data.historicalPE;
  const avgPE = peHistory.reduce((a, b) => a + b, 0) / peHistory.length;
  const peTrend = peHistory.length >= 10
    ? (peHistory[peHistory.length - 1] > peHistory[peHistory.length - 10] ? '上行' : '下行')
    : '稳定';

  tab.innerHTML = `
    <div class="card">
      <div class="card-title"><span class="emoji">📊</span>中期复盘（1-3个月）</div>
      <div class="data-grid">
        <div class="data-item">
          <div class="data-label">30日涨跌幅</div>
          <div class="data-value ${midChange >= 0 ? 'green' : 'red'}">${midChange >= 0 ? '+' : ''}${midChange.toFixed(2)}%</div>
        </div>
        <div class="data-item">
          <div class="data-label">30日最高/最低</div>
          <div class="data-value small">${high30.toFixed(0)} / ${low30.toFixed(0)}</div>
        </div>
        <div class="data-item">
          <div class="data-label">年化波动率</div>
          <div class="data-value ${volatility > 25 ? 'orange' : 'green'}">${volatility.toFixed(1)}%</div>
          <div class="data-sub">${volatility > 25 ? '高波动' : '正常波动'}</div>
        </div>
        <div class="data-item">
          <div class="data-label">PE趋势</div>
          <div class="data-value ${peTrend === '下行' ? 'green' : peTrend === '上行' ? 'orange' : 'blue'}">${peTrend}</div>
          <div class="data-sub">均值${avgPE.toFixed(1)}倍</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><span class="emoji">💡</span>中期操作建议</div>
      <div style="font-size:14px;line-height:1.8;color:var(--text-secondary)">
        ${generateMidTermAdvice(data, volatility, peTrend)}
      </div>
    </div>

    <div class="card">
      <div class="card-title"><span class="emoji">📐</span>定投成本分析</div>
      <div style="font-size:14px;line-height:1.8;color:var(--text-secondary)">
        ${(() => {
          const history = getInvestHistory();
          const totalInvested = history.reduce((sum, h) => sum + h.amount, 0);
          const totalShares = totalInvested / 1000;
          if (totalShares > 0) {
            const investedRatio = ((totalInvested / userSettings.totalAssets) * 100).toFixed(2);
            return `
              <div class="data-grid">
                <div class="data-item">
                  <div class="data-label">累计投入</div>
                  <div class="data-value">${formatAmount(totalShares)}元</div>
                </div>
                <div class="data-item">
                  <div class="data-label">占总资产比</div>
                  <div class="data-value blue">${investedRatio}%</div>
                </div>
                <div class="data-item">
                  <div class="data-label">操作次数</div>
                  <div class="data-value">${history.length}次</div>
                </div>
              </div>
            `;
          }
          return '暂无定投记录，开始定投后可查看成本分析。';
        })()}
      </div>
    </div>
  `;
}

function renderLongTermTab(data) {
  const tab = document.getElementById('tab-long');
  const pe = data.pe;
  const persuasion = generateDataPersuasion(data);

  // 长期PE百分位（模拟）
  const pePercentile = calculatePEPercentile(pe);

  tab.innerHTML = `
    <div class="card">
      <div class="card-title"><span class="emoji">🌐</span>长期趋势（1年+）</div>
      <div class="data-grid">
        <div class="data-item">
          <div class="data-label">当前PE</div>
          <div class="data-value ${data.peGrade.color}">${pe.toFixed(1)}倍</div>
        </div>
        <div class="data-item">
          <div class="data-label">PE历史百分位</div>
          <div class="data-value ${pePercentile < 30 ? 'green' : pePercentile > 70 ? 'red' : 'blue'}">${pePercentile.toFixed(0)}%</div>
          <div class="data-sub">${pePercentile < 30 ? '低估区间' : pePercentile > 70 ? '高估区间' : '合理区间'}</div>
        </div>
        <div class="data-item">
          <div class="data-label">12月正收益概率</div>
          <div class="data-value green">${persuasion.prob12m}</div>
        </div>
        <div class="data-item">
          <div class="data-label">预估最大浮亏</div>
          <div class="data-value orange">${persuasion.maxDrawdownPct}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title"><span class="emoji">🎯</span>长期策略建议</div>
      <div style="font-size:14px;line-height:1.8;color:var(--text-secondary)">
        ${generateLongTermAdvice(data, pePercentile)}
      </div>
    </div>

    <div class="card">
      <div class="card-title"><span class="emoji">📜</span>定投铁律回顾</div>
      <div style="font-size:13px;line-height:2;color:var(--text-secondary)">
        <div>1️⃣ 定投日基准金额，按PE档位自动调整</div>
        <div>2️⃣ 加仓仅限周一/二/三/五，单日封顶基础金额</div>
        <div>3️⃣ PE&lt;25加倍 | 25-28为1.5倍 | 28-32正常 | 32-35半额 | 35-40最低 | &gt;40暂停</div>
        <div>4️⃣ 跌2-4%加仓0.5倍 | 跌≥4%加仓1倍 | 跌≥7%极端超跌</div>
        <div>5️⃣ 一级事件前1日、VIX&gt;30+周跌&gt;5%、年末季末 → 降一档</div>
        <div>6️⃣ 每周定投占总资产仅${persuasion.weeklyRatio}%，执行它，关掉软件</div>
      </div>
    </div>

    <div class="card quote-card">
      <div class="quote-text">
        定投的本质是用时间换空间，用纪律战胜人性。<br>
        纳指长期年化收益约10-15%，短期波动是收集廉价份额的机会。<br>
        <strong>坚持3年以上，大概率跑赢任何主动管理策略。</strong>
      </div>
    </div>
  `;
}

function renderHistoryTab() {
  const tab = document.getElementById('tab-history');
  const history = getInvestHistory();

  if (history.length === 0) {
    tab.innerHTML = `
      <div class="card">
        <div class="card-title"><span class="emoji">📝</span>定投记录</div>
        <div style="text-align:center;padding:40px 0;color:var(--text-muted);">
          <div style="font-size:48px;margin-bottom:12px;">📋</div>
          <div>暂无定投记录</div>
          <div style="font-size:12px;margin-top:8px;">记录将自动保存在本地</div>
        </div>
      </div>
      <div style="text-align:center;margin-top:8px;">
        <button onclick="showAddRecordForm()" style="padding:8px 16px;background:rgba(34,197,94,0.15);color:var(--accent-green);border:1px solid rgba(34,197,94,0.3);border-radius:8px;font-size:12px;cursor:pointer;">➕ 手动添加记录</button>
      </div>
    `;
    return;
  }

  const totalInvested = history.reduce((sum, h) => sum + h.amount, 0);
  const totalShares = totalInvested / 1000;

  tab.innerHTML = `
    <div class="card">
      <div class="card-title"><span class="emoji">📝</span>定投记录</div>
      <div class="data-grid" style="margin-bottom:12px;">
        <div class="data-item">
          <div class="data-label">累计投入</div>
          <div class="data-value">${formatAmount(totalShares)}元</div>
        </div>
        <div class="data-item">
          <div class="data-label">操作次数</div>
          <div class="data-value">${history.length}次</div>
        </div>
      </div>
      ${history.slice().reverse().map(h => `
        <div class="history-item">
          <span class="history-date">${h.date}</span>
          <span class="history-action">${h.type}</span>
          <span class="history-amount ${h.amount > 0 ? 'green' : 'muted'}">${h.amount > 0 ? '+' : ''}${h.amount}元</span>
        </div>
      `).join('')}
    </div>
    <div style="text-align:center;margin-top:8px;display:flex;gap:8px;justify-content:center;">
      <button onclick="showAddRecordForm()" style="padding:8px 16px;background:rgba(34,197,94,0.15);color:var(--accent-green);border:1px solid rgba(34,197,94,0.3);border-radius:8px;font-size:12px;cursor:pointer;">➕ 手动添加记录</button>
      <button onclick="clearManualHistory()" style="padding:8px 16px;background:rgba(234,179,8,0.15);color:var(--accent-yellow);border:1px solid rgba(234,179,8,0.3);border-radius:8px;font-size:12px;cursor:pointer;">清空手动记录</button>
      <button onclick="clearAllHistory()" style="padding:8px 16px;background:rgba(239,68,68,0.15);color:var(--accent-red);border:1px solid rgba(239,68,68,0.3);border-radius:8px;font-size:12px;cursor:pointer;">清空全部</button>
    </div>
  `;
}

// ===== 建议生成函数 =====

function generateShortTermAdvice(data, addResult, trend) {
  const parts = [];

  // 今日操作
  if (data.isThursday) {
    parts.push(`<strong class="${data.peGrade.color}">今天是定投日，执行${formatAmount(data.peGrade.shares)}元定投。</strong>`);
  } else if (data.isTradingDay) {
    if (addResult.shouldAdd) {
      parts.push(`<strong class="green">今日可加仓${formatAmount(addResult.shares)}元。</strong>原因：${addResult.step1}`);
    } else {
      parts.push(`<strong class="muted">今日不加仓。</strong>${addResult.reason || ''}`);
    }
  } else {
    parts.push('今日非交易日，无需操作。');
  }

  // 短期趋势
  if (data.ndx.drawdown > 10) {
    parts.push('短期回撤较大，关注PE档位变化。若PE降至28以下，恢复正常档位定投。');
  } else if (data.ndx.change > 3) {
    parts.push('短期涨幅较大，注意不要追高。按规则只在跌幅触发时加仓。');
  } else {
    parts.push('短期波动正常，坚持既定定投纪律。');
  }

  // VIX提醒
  if (data.vix > 25) {
    parts.push(`VIX=${data.vix.toFixed(1)}偏高，市场波动加剧。保持纪律，不因恐慌暂停定投。`);
  }

  return parts.join('<br><br>');
}

function generateMidTermAdvice(data, volatility, peTrend) {
  const parts = [];

  // 波动率分析
  if (volatility > 30) {
    parts.push('中期波动率较高，市场不确定性增加。这是定投策略发挥优势的环境——波动越大，收集筹码的成本越平均。');
  } else if (volatility < 15) {
    parts.push('中期波动率较低，市场运行平稳。坚持定投，为下一轮波动积累筹码。');
  } else {
    parts.push('中期波动率处于正常范围，定投策略稳步推进。');
  }

  // PE趋势
  if (peTrend === '下行') {
    parts.push('PE呈下行趋势，意味着同样份数可以买到更多份额。这是定投的黄金时期，不要因为浮亏而停止。');
  } else if (peTrend === '上行') {
    parts.push('PE呈上行趋势，估值在抬高。按规则降低档位，控制投入节奏。');
  }

  // 中期建议
  if (data.pe > 35) {
    parts.push('当前PE偏高，中期建议维持最低档定投，不额外加仓。等待估值回归后再加大投入。');
  } else if (data.pe < 25) {
    parts.push('当前PE处于低估区间，中期建议加倍定投，积极收集廉价份额。这是超额收益的来源。');
  } else {
    parts.push('当前PE处于合理区间，中期建议按正常档位定投，保持节奏。');
  }

  return parts.join('<br><br>');
}

function generateLongTermAdvice(data, pePercentile) {
  const parts = [];

  // 百分位分析
  if (pePercentile < 20) {
    parts.push('当前PE处于历史低位（<20%分位），长期来看是极佳的定投窗口。历史上从这一水平开始定投，3年正收益概率超过90%。建议积极投入。');
  } else if (pePercentile < 50) {
    parts.push('当前PE处于历史中低位（<50%分位），长期定投胜率较高。保持纪律，坚持每周定投。');
  } else if (pePercentile < 80) {
    parts.push('当前PE处于历史中高位（50-80%分位），定投仍可继续但需控制节奏。按规则执行，不随意加码。');
  } else {
    parts.push('当前PE处于历史高位（>80%分位），需警惕估值回归风险。维持最低档定投，不追高。耐心等待回调机会。');
  }

  // 长期视角
  parts.push('纳指代表美国科技核心资产，长期年化收益约10-15%。定投策略的核心优势在于"低买高平均"，通过纪律性买入平滑成本。');
  parts.push('建议至少坚持3年以上。历史数据显示，持有纳指3年以上正收益概率超过85%。短期浮亏是长期收益的代价。');

  return parts.join('<br><br>');
}

// ===== PE百分位计算（模拟）=====
function calculatePEPercentile(currentPE) {
  // 基于纳指历史PE分布的近似计算
  // 纳指PE历史范围约15-50，中位数约25-28
  const mean = 27;
  const std = 6;

  // 使用正态分布近似
  const z = (currentPE - mean) / std;
  // 近似累积分布函数
  const percentile = 0.5 * (1 + erf(z / Math.sqrt(2)));
  return percentile * 100;
}

function erf(x) {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
  const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x >= 0 ? 1 : -1;
  x = Math.abs(x);
  const t = 1.0 / (1.0 + p * x);
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
  return sign * y;
}

// ===== 工具函数 =====

function getNYTime() {
  const now = new Date();
  // 转换为美东时间
  const nyTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  return nyTime;
}

function formatDateStr(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function formatTime(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${d} ${h}:${min}`;
}

function getDayName(day) {
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][day];
}

// ===== Tab切换 =====

function switchTab(tabName, btnElement) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

  if (btnElement) {
    btnElement.classList.add('active');
  } else {
    const btn = document.querySelector(`.tab-btn[onclick*="'${tabName}'"]`);
    if (btn) btn.classList.add('active');
  }
  document.getElementById(`tab-${tabName}`).classList.add('active');
}

// ===== 刷新数据 =====

async function refreshData() {
  const loading = document.getElementById('loadingState');
  const error = document.getElementById('errorState');
  const refreshBtn = document.getElementById('refreshBtn');

  // 显示加载状态
  loading.style.display = 'flex';
  error.style.display = 'none';
  if (refreshBtn) refreshBtn.classList.add('spinning');

  try {
    const data = await fetchAllMarketData();
    marketData = data;

    // 隐藏加载
    loading.style.display = 'none';

    // 渲染
    renderAllTabs(data);
    updateHeaderStatus(data);

    // 记录今日定投
    if (!data._mock && !data._stale) {
      recordTodayInvest(data);
    }

  } catch (err) {
    console.error('Data fetch error:', err);
    loading.style.display = 'none';

    // 如果有缓存数据，即使刷新失败也显示缓存
    if (marketData) {
      renderAllTabs(marketData);
      updateHeaderStatus({...marketData, _stale: true});
    } else {
      error.style.display = 'block';
      document.getElementById('errorMsg').textContent = `数据加载失败: ${err.message}`;
      const statusBadge = document.getElementById('statusBadge');
      const statusText = document.getElementById('statusText');
      if (statusBadge) statusBadge.className = 'status-badge error';
      if (statusText) statusText.textContent = '离线';
    }
  } finally {
    if (refreshBtn) refreshBtn.classList.remove('spinning');
  }
}

// ===== 设置管理 =====

function loadSettings() {
  try {
    const saved = localStorage.getItem('nasdaq_dca_settings');
    const checksum = localStorage.getItem('nasdaq_dca_settings_checksum');
    if (saved) {
      if (checksum && computeChecksum(saved) !== checksum) {
        console.warn('Settings checksum mismatch, using defaults');
        return;
      }
      const parsed = JSON.parse(saved);
      userSettings = { ...userSettings, ...parsed };
    }
  } catch (e) {
    console.warn('Settings load failed:', e);
  }
}

function saveSettings() {
  const data = JSON.stringify(userSettings);
  localStorage.setItem('nasdaq_dca_settings', data);
  localStorage.setItem('nasdaq_dca_settings_checksum', computeChecksum(data));
  closeSettings();

  // 重新渲染
  if (marketData) {
    renderTodayTab(marketData);
    renderShortTermTab(marketData);
    renderMidTermTab(marketData);
    renderLongTermTab(marketData);
  }
}

function toggleSettings() {
  renderProfileUI();
  document.getElementById('settingsOverlay').classList.add('show');
}

function closeSettings(e) {
  if (!e || e.target === document.getElementById('settingsOverlay')) {
    document.getElementById('settingsOverlay').classList.remove('show');
  }
}

// ===== 定投记录 =====

function getInvestHistory(profileId) {
  try {
    const saved = localStorage.getItem('nasdaq_dca_history');
    const checksum = localStorage.getItem('nasdaq_dca_history_checksum');
    let all = [];
    if (saved) {
      if (checksum && computeChecksum(saved) !== checksum) {
        console.warn('History checksum mismatch, returning empty');
        return [];
      }
      all = JSON.parse(saved);
    }
    // 如果指定了 profileId，则只返回该角色的记录
    if (profileId) {
      return all.filter(h => h.profileId === profileId);
    }
    // 默认返回当前角色的记录
    return all.filter(h => h.profileId === currentProfileId);
  } catch (e) {
    return [];
  }
}

function recordTodayInvest(data) {
  const today = formatDateStr(new Date());

  // 读取全部历史记录（不过滤角色）
  let allHistory = [];
  try {
    const saved = localStorage.getItem('nasdaq_dca_history');
    const checksum = localStorage.getItem('nasdaq_dca_history_checksum');
    if (saved) {
      if (checksum && computeChecksum(saved) !== checksum) {
        console.warn('History checksum mismatch, using empty');
        allHistory = [];
      } else {
        allHistory = JSON.parse(saved);
      }
    }
  } catch (e) {
    allHistory = [];
  }

  // 检查今天是否已记录（当前角色）
  if (allHistory.find(h => h.date === today && h.profileId === currentProfileId)) return;

  const grade = data.peGrade;
  const addResult = calculateAdditionalBuy(data);

  const records = [];

  // 周四定投记录（amount保留为内部金额，用于计算）
  if (data.isThursday && grade.shares > 0) {
    records.push({
      date: today,
      type: '周四定投',
      amount: grade.shares * userSettings.baseAmount,
      shares: grade.shares,
      pe: data.pe,
      ndx: data.ndx.price,
      profileId: currentProfileId,
    });
  }

  // 加仓记录
  if (addResult.shouldAdd && addResult.shares > 0) {
    records.push({
      date: today,
      type: '额外加仓',
      amount: addResult.shares * userSettings.baseAmount,
      shares: addResult.shares,
      pe: data.pe,
      ndx: data.ndx.price,
      profileId: currentProfileId,
    });
  }

  if (records.length > 0) {
    allHistory.push(...records);
    const dataStr = JSON.stringify(allHistory);
    localStorage.setItem('nasdaq_dca_history', dataStr);
    localStorage.setItem('nasdaq_dca_history_checksum', computeChecksum(dataStr));
  }
}

function clearHistory() {
  clearAllHistory();
}

function clearManualHistory() {
  if (confirm('确定要清空手动添加的记录吗？默认角色的初始记录将保留。')) {
    let allHistory = [];
    try {
      const saved = localStorage.getItem('nasdaq_dca_history');
      const checksum = localStorage.getItem('nasdaq_dca_history_checksum');
      if (saved) {
        if (checksum && computeChecksum(saved) !== checksum) {
          allHistory = [];
        } else {
          allHistory = JSON.parse(saved);
        }
      }
    } catch (e) {
      allHistory = [];
    }
    // 只删除手动添加的记录（isManual=true），保留默认初始记录
    allHistory = allHistory.filter(h => {
      if (h.profileId !== currentProfileId) return true;
      if (h.date === '2026-06-05' && h.profileId === 'default') return true;
      if (!h.isManual) return true;
      return false;
    });
    const dataStr = JSON.stringify(allHistory);
    localStorage.setItem('nasdaq_dca_history', dataStr);
    localStorage.setItem('nasdaq_dca_history_checksum', computeChecksum(dataStr));
    renderHistoryTab();
  }
}

function clearAllHistory() {
  if (confirm('确定要清空当前角色的所有定投记录吗？默认角色的初始记录（2026-06-05）将保留。')) {
    let allHistory = [];
    try {
      const saved = localStorage.getItem('nasdaq_dca_history');
      const checksum = localStorage.getItem('nasdaq_dca_history_checksum');
      if (saved) {
        if (checksum && computeChecksum(saved) !== checksum) {
          allHistory = [];
        } else {
          allHistory = JSON.parse(saved);
        }
      }
    } catch (e) {
      allHistory = [];
    }
    // 保留默认角色的初始记录
    allHistory = allHistory.filter(h => {
      if (h.profileId !== currentProfileId) return true;
      if (h.date === '2026-06-05' && h.profileId === 'default') return true;
      return false;
    });
    const dataStr = JSON.stringify(allHistory);
    localStorage.setItem('nasdaq_dca_history', dataStr);
    localStorage.setItem('nasdaq_dca_history_checksum', computeChecksum(dataStr));
    renderHistoryTab();
  }
}

function showAddRecordForm() {
  const today = formatDateStr(new Date());
  const tab = document.getElementById('tab-history');
  // 在tab顶部插入表单（如果已存在则先移除）
  const existingForm = document.getElementById('manualRecordForm');
  if (existingForm) {
    existingForm.remove();
    return;
  }

  const formHTML = `
    <div id="manualRecordForm" class="card" style="border:1px solid var(--accent-green);">
      <div class="card-title"><span class="emoji">➕</span>手动添加记录</div>
      <div class="setting-group">
        <div class="setting-label">日期</div>
        <input type="date" class="setting-input" id="manualRecordDate" value="${today}">
      </div>
      <div class="setting-group">
        <div class="setting-label">类型</div>
        <select class="setting-input" id="manualRecordType" style="background:var(--bg-card);color:var(--text-primary);">
          <option value="周四定投">周四定投</option>
          <option value="额外加仓">额外加仓</option>
        </select>
      </div>
      <div class="setting-group">
        <div class="setting-label">金额(元)</div>
        <input type="number" class="setting-input" id="manualRecordShares" value="1" step="0.1" min="0.1">
      </div>
      <div style="display:flex;gap:8px;">
        <button onclick="saveManualRecord()" class="settings-save" style="flex:1;background:var(--accent-green);">保存</button>
        <button onclick="document.getElementById('manualRecordForm').remove()" class="settings-save" style="flex:1;background:var(--text-muted);">取消</button>
      </div>
    </div>
  `;
  tab.insertAdjacentHTML('afterbegin', formHTML);
}

function saveManualRecord() {
  const date = document.getElementById('manualRecordDate').value;
  const type = document.getElementById('manualRecordType').value;
  const shares = parseFloat(document.getElementById('manualRecordShares').value) || 1;

  if (!date) {
    alert('请选择日期');
    return;
  }

  let allHistory = [];
  try {
    const saved = localStorage.getItem('nasdaq_dca_history');
    const checksum = localStorage.getItem('nasdaq_dca_history_checksum');
    if (saved) {
      if (checksum && computeChecksum(saved) !== checksum) {
        allHistory = [];
      } else {
        allHistory = JSON.parse(saved);
      }
    }
  } catch (e) {
    allHistory = [];
  }

  // 检查该日期是否已有同类型记录（当前角色）
  const exists = allHistory.find(h => h.date === date && h.type === type && h.profileId === currentProfileId);
  if (exists) {
    if (!confirm(`该日期已有${type}记录，是否继续添加？`)) return;
  }

  const record = {
    date: date,
    type: type,
    amount: shares * 1000,
    shares: shares,
    pe: marketData ? marketData.pe : 0,
    ndx: marketData ? marketData.ndx.price : 0,
    profileId: currentProfileId,
    isManual: true,
  };

  allHistory.push(record);
  const dataStr = JSON.stringify(allHistory);
  localStorage.setItem('nasdaq_dca_history', dataStr);
  localStorage.setItem('nasdaq_dca_history_checksum', computeChecksum(dataStr));

  // 移除表单并刷新
  const form = document.getElementById('manualRecordForm');
  if (form) form.remove();
  renderHistoryTab();
}

// ===== 数据缓存 =====

function saveCachedData(data) {
  try {
    const payload = JSON.stringify({
      timestamp: data.timestamp,
      data: data,
    });
    localStorage.setItem('nasdaq_dca_cache', payload);
  } catch (e) {
    console.warn('Cache save failed:', e);
  }
}

function loadCachedData() {
  try {
    const saved = localStorage.getItem('nasdaq_dca_cache');
    if (saved) {
      const parsed = JSON.parse(saved);
      return parsed.data;
    }
  } catch (e) {
    console.warn('Cache load failed:', e);
  }
  return null;
}

// ===== 模拟数据生成 =====

function generateMockData() {
  const today = getNYTime();
  const dayOfWeek = today.getDay();
  const isTradingDay = dayOfWeek >= 1 && dayOfWeek <= 5;
  const isThursday = dayOfWeek === 4;

  // 模拟价格（基于近期纳指大致水平）
  const basePrice = 21000;
  const priceVariation = (Math.random() - 0.5) * 400;
  const currentPrice = basePrice + priceVariation;
  const prevClose = currentPrice - (Math.random() - 0.5) * 200;
  const dailyChange = ((currentPrice - prevClose) / prevClose * 100);

  // 生成模拟历史收盘价
  const recentCloses = [];
  for (let i = 30; i >= 0; i--) {
    recentCloses.push(currentPrice - i * (Math.random() * 50 + 10) + (Math.random() - 0.5) * 300);
  }

  const ma20 = recentCloses.slice(-20).reduce((a, b) => a + b, 0) / 20;
  const high60d = Math.max(...recentCloses);
  const drawdown = ((high60d - currentPrice) / high60d * 100);

  const weekAgoPrice = recentCloses[recentCloses.length - 6] || currentPrice;
  const weeklyChange = ((currentPrice - weekAgoPrice) / weekAgoPrice * 100);

  // 模拟PE
  const pe = estimatePE(currentPrice);

  // 模拟VIX
  const vix = 15 + Math.random() * 15;

  // 模拟美债收益率
  const treasury10y = 4.0 + Math.random() * 1.0;

  // 距周四
  let daysToThursday = (4 - dayOfWeek + 7) % 7;
  if (daysToThursday === 0 && isTradingDay) daysToThursday = 0;
  else if (daysToThursday === 0) daysToThursday = 7;

  // 股债性价比
  const equityBondRatio = (1.5 / treasury10y).toFixed(2);

  // 历史PE
  const historicalPE = recentCloses.map(c => estimatePE(c));

  const data = {
    timestamp: Date.now(),
    nyTime: today,
    _mock: true,

    ndx: {
      price: currentPrice,
      prevClose: prevClose,
      change: dailyChange,
      weeklyChange: weeklyChange,
      high60d: high60d,
      drawdown: drawdown,
      ma20: ma20,
      ma20Direction: currentPrice > ma20 ? 'up' : 'down',
      recentCloses: recentCloses,
      timestamps: [],
    },

    pe: pe,
    peGrade: getPEGrade(pe),

    vix: vix,
    vixRecent: [vix - 1, vix + 0.5, vix - 0.3, vix + 1, vix],

    treasury10y: treasury10y,
    equityBondRatio: equityBondRatio,

    isTradingDay: isTradingDay,
    isThursday: isThursday,
    daysToThursday: daysToThursday,
    dayOfWeek: dayOfWeek,

    historicalPE: historicalPE,
  };

  marketData = data;
  lastFetchTime = Date.now();
  return data;
}
