#!/bin/bash
# relay_run_trading.sh — 阿里云中继 Trading System 全链路运行脚本
# 2026-11-12 迁移自 GitHub Actions schedule（trading-system.yml）：
#   GitHub schedule 触发器高负载日静默失守（2026-11-12 上午实锤三 workflow 全 miss），
#   中继为 7x24 境内机器，cron 触发可靠性归自己，且东财对境内 IP 不限流。
# 用法: /opt/ts_repo/scripts/relay_run_trading.sh   （cron 11:00/14:30 北京时间, 周一至五）
set -euo pipefail
cd /opt/ts_repo
export TZ=Asia/Shanghai
mkdir -p logs
LOG="logs/ts_$(date +'%Y%m%d').log"
echo "[$(date +'%F %T')] === relay run start ===" >>"$LOG"

# 0) 同步远端（防多端并行撞车）
git pull --rebase origin main >>"$LOG" 2>&1

# 1) 五模块主流水线
python3 trading_system.py >>"$LOG" 2>&1

# 2) q75 执行器
python3 q75/q75_executor.py >>"$LOG" 2>&1

# 3) 前瞻记录器
python3 q75/jq_forward_logger.py >>"$LOG" 2>&1

# 4) 面板产物组装（与 workflow Copy/Run 步骤一致）
cp hub.html output/hub.html
cp data.json output/main-data.json
cp CNAME output/CNAME
cp jq_panel.json output/jq_panel.json 2>/dev/null || echo '{"error":"jq_panel not generated"}' > output/jq_panel.json
cp q75/q75_signal.json output/q75_signal.json
cp q75/q75_trades.json output/q75_trades.json 2>/dev/null || echo "[]" > output/q75_trades.json
cp q75/q75_ledger.json output/q75_ledger.json 2>/dev/null || true
cp q75/jq_forward_log.jsonl output/jq_forward_log.jsonl 2>/dev/null || true
cp q75/q75_signal.json q75_signal.json
cp q75/q75_trades.json q75_trades.json 2>/dev/null || echo "[]" > q75_trades.json
cp q75/q75_ledger.json q75_ledger.json 2>/dev/null || true
cp q75/jq_forward_log.jsonl jq_forward_log.jsonl 2>/dev/null || true

# 5) 数据闸门（残缺扫描不许上面板，账本 commit 照常）
python3 - <<'PYEOF' >>"$LOG" 2>&1
import json, sys
d = json.load(open("output/trading_data.json", encoding="utf-8"))
scanned = (d.get("module_2_selection") or {}).get("scanned") or 0
if scanned < 20:
    sys.exit(f"GATE FAIL: scanned={scanned} < 20 (panel NOT deployed)")
print(f"GATE PASS: scanned={scanned}")
PYEOF

# 6) commit + push（pull --rebase 防撞车）
git config user.name "jivon-relay[bot]"
git config user.email "secretary@jivonlab.com"
git add output/trading_data.json output/index.html index.html cache/trading_history.json \
        cache/ts_board_kline_cache.json q75/q75_signal.json q75/q75_trades.json q75/q75_ledger.json \
        q75/jq_forward_log.jsonl q75_signal.json q75_trades.json q75_ledger.json jq_forward_log.jsonl || true
git diff --staged --quiet || git commit -m "auto: trading system update $(date +'%Y-%m-%d %H:%M')"
git pull --rebase origin main >>"$LOG" 2>&1 || git pull --rebase origin main >>"$LOG" 2>&1
git push origin main >>"$LOG" 2>&1

# 7) gh-pages 部署（worktree 方式复刻 peaceiris force_orphan 效果）
git fetch origin gh-pages >>"$LOG" 2>&1
git worktree add --detach /opt/ts_deploy origin/gh-pages >>"$LOG" 2>&1 || true
rm -rf /opt/ts_deploy/* 2>/dev/null || true
cp -r output/. /opt/ts_deploy/
rm -f /opt/ts_deploy/.git 2>/dev/null || true
touch /opt/ts_deploy/.nojekyll
cd /opt/ts_deploy
git add -A
git commit -m "deploy: trading dashboard $(date +'%Y-%m-%d %H:%M')" --allow-empty -q || true
git push --force origin HEAD:gh-pages >>"$LOG" 2>&1

echo "[$(date +'%F %T')] run complete" >>"$LOG"
