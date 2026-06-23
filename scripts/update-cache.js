/**
 * 市场数据缓存更新脚本
 * 由 GitHub Actions 定时运行，每15分钟更新一次
 * 直接从 Yahoo Finance 获取数据（服务端无CORS限制）
 */

const https = require('https');

// ===== 配置 =====
const SYMBOLS = {
  NDX: '^NDX',
  VIX: '^VIX',
  TNX: '^TNX',
  SPY: 'SPY',
  QQQ: 'QQQ',
};

const YAHOO_BASE = 'query1.finance.yahoo.com';

// ===== 工具函数 =====
function httpGet(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      }
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return httpGet(res.headers.location).then(resolve).catch(reject);
      }
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error('JSON parse error: ' + data.substring(0, 200))); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('Timeout')); });
  });
}

function fetchChartData(symbol, range = '1mo', interval = '1d') {
  const url = `https://${YAHOO_BASE}/v8/finance/chart/${symbol}?interval=${interval}&range=${range}&includePrePost=false`;
  return httpGet(url);
}

// ===== PE估算 =====
function estimatePE(price) {
  // 基于已知数据点建立价格-PE映射
  // 数据来源：Siblis Research + Yahoo Finance，覆盖2020-2025年关键价格-PE对应关系
  const knownPoints = [
    { price: 7500,  pe: 22.5, date: '2020-03' },
    { price: 11000, pe: 30.2, date: '2020-09' },
    { price: 13000, pe: 32.5, date: '2021-01' },
    { price: 14500, pe: 28.8, date: '2021-07' },
    { price: 15000, pe: 25.5, date: '2022-01' },
    { price: 10500, pe: 20.8, date: '2022-10' },
    { price: 10500, pe: 23.5, date: '2023-01' },
    { price: 15500, pe: 29.0, date: '2023-07' },
    { price: 17000, pe: 28.5, date: '2024-01' },
    { price: 19000, pe: 30.5, date: '2024-07' },
    { price: 21000, pe: 33.0, date: '2025-01' },
    { price: 22000, pe: 34.5, date: '2025-06' },
  ];

  if (price <= knownPoints[0].price) return knownPoints[0].pe;
  if (price >= knownPoints[knownPoints.length - 1].price) {
    // 外推：每涨1000点，PE约增加0.8
    const last = knownPoints[knownPoints.length - 1];
    return last.pe + ((price - last.price) / 1000) * 0.8;
  }

  // 线性插值
  for (let i = 0; i < knownPoints.length - 1; i++) {
    if (price >= knownPoints[i].price && price <= knownPoints[i + 1].price) {
      const ratio = (price - knownPoints[i].price) / (knownPoints[i + 1].price - knownPoints[i].price);
      return knownPoints[i].pe + ratio * (knownPoints[i + 1].pe - knownPoints[i].pe);
    }
  }
  return 30; // 默认值
}

function getPEGrade(pe) {
  if (pe <= 25) return { name: '加倍', amount: 2000, color: 'green', cls: 'buy-double' };
  if (pe <= 28) return { name: '1.5倍', amount: 1500, color: 'blue', cls: 'buy-normal' };
  if (pe <= 32) return { name: '正常', amount: 1000, color: 'blue', cls: 'buy-normal' };
  if (pe <= 35) return { name: '半额', amount: 500, color: 'yellow', cls: 'buy-half' };
  if (pe <= 40) return { name: '最低', amount: 300, color: 'orange', cls: 'buy-min' };
  return { name: '暂停', amount: 0, color: 'red', cls: 'buy-zero' };
}

function getNYTime() {
  const now = new Date();
  // 转换为美东时间
  const nyTimeStr = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
  return new Date(nyTimeStr);
}

// ===== 主流程 =====
async function main() {
  console.log('开始更新市场数据缓存...');
  const now = Date.now();
  const nyTime = getNYTime();

  try {
    // 并行获取所有数据
    const [ndxData, vixData, tnxData] = await Promise.all([
      fetchChartData(SYMBOLS.NDX, '2mo', '1d'),
      fetchChartData(SYMBOLS.VIX, '5d', '1d'),
      fetchChartData(SYMBOLS.TNX, '5d', '1d'),
    ]);

    // 解析纳指数据
    const ndxMeta = ndxData.chart.result[0].meta;
    const ndxPrice = ndxMeta.regularMarketPrice;
    const ndxPrevClose = ndxMeta.chartPreviousClose || ndxMeta.previousClose;
    const dailyChange = ((ndxPrice - ndxPrevClose) / ndxPrevClose * 100);

    // 历史收盘价
    const timestamps = ndxData.chart.result[0].timestamp || [];
    const closes = ndxData.chart.result[0].indicators.quote[0].close || [];
    const recentCloses = closes.filter(c => c !== null);
    const recentTimestamps = timestamps.slice(-recentCloses.length);

    // 20日均线
    const last20 = recentCloses.slice(-20);
    const ma20 = last20.reduce((a, b) => a + b, 0) / last20.length;

    // 60日高点
    const high60d = Math.max(...recentCloses.slice(-60));
    const drawdown = ((high60d - ndxPrice) / high60d * 100);

    // 周涨跌
    const weekAgoIdx = recentCloses.length - 6;
    const weekAgoPrice = weekAgoIdx >= 0 ? recentCloses[weekAgoIdx] : ndxPrice;
    const weeklyChange = ((ndxPrice - weekAgoPrice) / weekAgoPrice * 100);

    // VIX
    const vixMeta = vixData.chart.result[0].meta;
    const vix = vixMeta.regularMarketPrice;
    const vixCloses = (vixData.chart.result[0].indicators.quote[0].close || []).filter(c => c !== null);

    // 美债收益率
    const tnxMeta = tnxData.chart.result[0].meta;
    const treasury10y = tnxMeta.regularMarketPrice;

    // PE
    const pe = estimatePE(ndxPrice);
    const peGrade = getPEGrade(pe);

    // 股债性价比
    const equityBondRatio = (1.5 / treasury10y).toFixed(2);

    // 交易日判断
    const dayOfWeek = nyTime.getDay();
    const isTradingDay = dayOfWeek >= 1 && dayOfWeek <= 5;
    const isThursday = dayOfWeek === 4;
    let daysToThursday = (4 - dayOfWeek + 7) % 7;
    if (daysToThursday === 0 && isTradingDay) daysToThursday = 0;
    else if (daysToThursday === 0) daysToThursday = 7;

    // 历史PE
    const historicalPE = recentCloses.map(c => estimatePE(c));

    // 构建缓存数据
    const cache = {
      timestamp: now,
      nyTime: nyTime.toISOString(),
      ndx: {
        price: ndxPrice,
        prevClose: ndxPrevClose,
        change: dailyChange,
        weeklyChange: weeklyChange,
        high60d: high60d,
        drawdown: drawdown,
        ma20: ma20,
        ma20Direction: ndxPrice > ma20 ? 'up' : 'down',
        recentCloses: recentCloses,
        timestamps: recentTimestamps,
      },
      pe: pe,
      peGrade: peGrade,
      vix: vix,
      vixRecent: vixCloses.slice(-5),
      treasury10y: treasury10y,
      equityBondRatio: equityBondRatio,
      isTradingDay: isTradingDay,
      isThursday: isThursday,
      daysToThursday: daysToThursday,
      dayOfWeek: dayOfWeek,
      historicalPE: historicalPE,
      dataSource: 'yahoo-finance-server',
      updatedAt: new Date().toISOString(),
    };

    // 合并同花顺数据（ths-cache.json）
    const fs = require('fs');
    const path = require('path');
    const thsCachePath = path.join(__dirname, '..', 'ths-cache.json');
    if (fs.existsSync(thsCachePath)) {
      try {
        const thsData = JSON.parse(fs.readFileSync(thsCachePath, 'utf-8'));
        cache.ths = thsData;
        cache.dataSource = 'yahoo-finance-server + thsdk';
        console.log(`   ✅ 已合并同花顺数据：${thsData.etfs?.length || 0} 只纳指ETF`);
      } catch (e) {
        console.warn('   ⚠️ 同花顺数据合并失败:', e.message);
      }
    }

    // 写入 cache.json
    fs.writeFileSync('cache.json', JSON.stringify(cache, null, 2));

    console.log(`✅ 缓存更新成功！`);
    console.log(`   纳指: ${ndxPrice.toFixed(0)} (${dailyChange >= 0 ? '+' : ''}${dailyChange.toFixed(2)}%)`);
    console.log(`   PE: ${pe.toFixed(1)} (${peGrade.name}档)`);
    console.log(`   VIX: ${vix.toFixed(1)}`);
    console.log(`   10Y美债: ${treasury10y.toFixed(2)}%`);

  } catch (err) {
    console.error('❌ 缓存更新失败:', err.message);
    process.exit(1);
  }
}

main();
