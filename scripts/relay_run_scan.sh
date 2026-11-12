#!/bin/bash
# relay_run_scan.sh — 阿里云中继 扫描/面板三模式运行脚本
# 2026-11-12 迁移自 GitHub Actions schedule（quick-money.yml / update.yml / right-side-scan.yml）：
#   与 trading-system 同批迁移（GitHub schedule 高负载日静默失守，2026-11-12 上午实锤三 workflow 全 miss）
# 用法: relay_run_scan.sh <quickmoney|update|scan>
#   quickmoney = quick_money.py  快钱板块扫描（原 GitHub 9-15 点每小时）
#   update     = update_data.py  面板 data.json 更新（原 GitHub 11:00/13:30）
#   scan       = scanner.py     MACD+KDJ 右侧扫描（原 GitHub 14:10）
set -uo pipefail
cd /opt/ts_repo
export TZ=Asia/Shanghai
MODE="${1:-}"
mkdir -p logs
LOG="logs/scan_$(date +'%Y%m%d').log"
echo "[$(date +'%F %T')] === relay scan:$MODE start ===" >>"$LOG"

gh_retry() {
    local desc="$1"; shift
    for i in 1 2 3 4 5; do
        if "$@" >>"$LOG" 2>&1; then return 0; fi
        echo "[gh_retry] $desc attempt $i failed, sleep 10s" >>"$LOG"
        sleep 10
    done
    echo "[gh_retry] $desc FAILED after 5 attempts" >>"$LOG"
    return 1
}

case "$MODE" in
    quickmoney) SCRIPT="quick_money.py" ;;
    update)     SCRIPT="update_data.py" ;;
    scan)       SCRIPT="scanner.py" ;;
    *) echo "[FATAL] unknown mode: $MODE (use quickmoney|update|scan)" >>"$LOG"; exit 1 ;;
esac

# 0) 同步远端
gh_retry "git pull ($MODE)" git pull --rebase origin main

# 1) 运行扫描脚本
python3 "$SCRIPT" >>"$LOG" 2>&1 || { echo "[FATAL] $SCRIPT failed" >>"$LOG"; exit 1; }

# 2) commit + push（按 workflow 原步骤的 git add 范围）
git config user.name "jivon-relay[bot]"
git config user.email "secretary@jivonlab.com"
case "$MODE" in
    quickmoney) git add quick_money.json cache/ 2>/dev/null || true ;;
    update)     git add data.json 2>/dev/null || true ;;
    scan)       git add scan/data.json 2>/dev/null || true ;;
esac
if git diff --staged --quiet; then
    echo "[$(date +'%F %T')] $MODE: no changes, skip commit" >>"$LOG"
else
    git commit -m "relay $MODE: data update $(date +'%Y-%m-%d %H:%M')" >>"$LOG" 2>&1
    gh_retry "git push ($MODE)" git push origin main
fi
echo "[$(date +'%F %T')] relay scan:$MODE complete" >>"$LOG"
