#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
em_board_fetch.py — 东财板块K线批量抓取（部署在阿里云中继 /opt/em_fetch.py）
用途: GitHub Actions Runner(境外IP)被东财限流时, 由境内中继代抓全部板块日K,
      输出单行JSON供 Runner 落 cache/ts_board_kline_cache.json 种子。
输出: {"boards": {"板块名": {"secid":..., "dates":[...], "open":[...], "close":[...],
                            "high":[...], "low":[...]}}, "fetched_at": "..."}
板块清单与 trading_system.py BOARDS 对齐(25个)。
码表沿革: 2026-11-11 修4个退役码; 2026-11-12 二次退役修14个(clist m:90 全量枚举实测名称匹配,
          科创芯片 BK0990 板块消失→BK0891 芯片概念, 其余13码被重分配见各行注释)。
v2 2026-11-12: timeout 15→25s、重试3→4次(指数退避)、节流0.8→1.5s、失败板块冷却45s后二次补扫
               (东财限流为滚动窗口, 首轮被掐的板块冷却后常可过); 首轮连续遇 RemoteDisconnected
               则全局冷却120s再跑第二轮, 避免把限流窗口越烧越深。
"""
import json
import ssl
import sys
import time
import urllib.request

BOARDS = {
    "科创芯片": "90.BK0891",  # 2026-11-12 板块消失 BK0990(被快递概念占用)→BK0891 芯片概念
    "存储芯片": "90.BK1137",  # 2026-11-12 BK1135→BK1137 (旧码被数据要素占用)
    "半导体": "90.BK1036",
    "先进封装": "90.BK1101",  # 2026-11-12 BK1032→BK1101 (旧码被风电设备占用)
    "汽车芯片": "90.BK0969",  # 2026-11-11 BK0962→BK0969
    "CPO": "90.BK1128",       # 2026-11-12 BK1099→BK1128 (现名CPO概念, 旧码被轮毂电机占用)
    "光通信": "90.BK1136",    # 2026-11-12 BK1098→BK1136 (现名光通信模块, 旧码被生物质能发电占用)
    "算力": "90.BK1134",      # 2026-11-12 确认现名"算力概念"码未变
    "液冷服务器": "90.BK1138",  # 2026-11-12 BK1156→BK1138 (旧码被PEEK材料占用)
    "铜缆高速连接": "90.BK1168",
    "PCB": "90.BK0877",
    "AI手机": "90.BK1162",
    "智能穿戴": "90.BK0641",  # 2026-11-11 BK0862→BK0641
    "消费电子": "90.BK1037",  # 2026-11-11 BK0878→BK1037
    "AI眼镜": "90.BK1178",    # 2026-11-12 BK1170→BK1178 (旧码被AI制药占用)
    "固态电池": "90.BK0968",
    "低空经济": "90.BK1166",
    "人形机器人": "90.BK1184",  # 2026-11-12 BK1158→BK1184 (旧码被微盘股占用)
    "商业航天": "90.BK0963",  # 2026-11-12 BK1161→BK0963 (旧码被英伟达概念占用)
    "创新药": "90.BK1106",    # 2026-11-12 BK0939→BK1106 (旧码被辅助生殖占用)
    "稀土永磁": "90.BK0578",  # 2026-11-12 BK0579→BK0578 (旧码被云计算占用)
    "数据要素": "90.BK1135",  # 2026-11-12 BK1142→BK1135 (旧码被裸眼3D占用, 即存储芯片旧码)
    "量子科技": "90.BK0710",  # 2026-11-12 BK1076→BK0710 (旧码被建筑节能占用)
    "脑机接口": "90.BK0706",  # 2026-11-12 BK1124→BK0706 (旧码被毫米波占用)
    "数字货币": "90.BK0883",  # 2026-11-11 BK0903→BK0883
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/126.0"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

URL_T = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?"
         "secid={secid}&fields1=f1,f2,f3,f4,f5,f6&"
         "fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
         "&klt=101&fqt=1&end=20500101&lmt=130")

TIMEOUT = 25          # 单请求超时(秒)
RETRIES = 4           # 单板块重试次数
THROTTLE = 1.5        # 板块间节流(秒)
COOLDOWN_AFTER_DISCONNECT = 120  # 首轮遇连接级秒断(RemoteDisconnected)后的全局冷却
RETRY_WAIT = 45       # 二次补扫前对失败板块的冷却(秒)


def fetch(secid, retries=RETRIES):
    """抓单板块, 指数退避重试; 返回 kline dict 或 None (main 不再用, 保留作单板块调试)"""
    last_exc = None
    for i in range(retries):
        try:
            req = urllib.request.Request(URL_T.format(secid=secid), headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
                d = json.loads(r.read().decode())
            kl = (d.get("data") or {}).get("klines") or []
            if kl:
                out = {"dates": [], "open": [], "close": [], "high": [], "low": []}
                for line in kl:
                    p = line.split(",")
                    out["dates"].append(p[0])
                    out["open"].append(float(p[1]))
                    out["close"].append(float(p[2]))
                    out["high"].append(float(p[3]))
                    out["low"].append(float(p[4]))
                return out
            # 有响应但无数据(常见=码退役): 不重试, 直接失败
            return None
        except Exception as e:
            last_exc = e
            # 连接级秒断说明限流加深, 退避加倍
            time.sleep(2 * (2 ** i) if "Disconnected" in type(e).__name__ else 2 * (i + 1))
    print(f"[fetch-fail] {secid}: {type(last_exc).__name__}" if last_exc else
          f"[fetch-fail] {secid}: empty", file=sys.stderr, flush=True)
    return None


def run_round_v(names):
    """同 run_round, 但检测连接级秒断"""
    ok, failed, saw_disc = {}, [], False
    for name in names:
        secid = BOARDS[name]
        got = None
        for i in range(RETRIES):
            try:
                req = urllib.request.Request(URL_T.format(secid=secid), headers=UA)
                with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
                    d = json.loads(r.read().decode())
                kl = (d.get("data") or {}).get("klines") or []
                if kl:
                    out = {"dates": [], "open": [], "close": [], "high": [], "low": []}
                    for line in kl:
                        p = line.split(",")
                        out["dates"].append(p[0])
                        out["open"].append(float(p[1]))
                        out["close"].append(float(p[2]))
                        out["high"].append(float(p[3]))
                        out["low"].append(float(p[4]))
                    got = out
                    break
                break  # 有响应但空数据=码退役, 不重试
            except Exception as e:
                if "Disconnected" in type(e).__name__:
                    saw_disc = True
                time.sleep(2 * (2 ** i) if "Disconnected" in type(e).__name__ else 2 * (i + 1))
        if got and len(got["dates"]) >= 25:
            got["secid"] = secid
            ok[name] = got
        else:
            failed.append(name)
        time.sleep(THROTTLE)
    return ok, failed, saw_disc


def main():
    from datetime import datetime
    all_boards, perm_failed = {}, []
    pending = list(BOARDS.keys())

    ok, failed, saw_disc = run_round_v(pending)
    all_boards.update(ok)

    # 首轮大面积连接级秒断 → 全局冷却后再补扫失败板块
    if saw_disc and failed:
        print(f"[cool] disconnect detected, cooldown {COOLDOWN_AFTER_DISCONNECT}s "
              f"then retry {len(failed)} failed boards", file=sys.stderr, flush=True)
        time.sleep(COOLDOWN_AFTER_DISCONNECT)
        ok2, failed2, _ = run_round_v(failed)
        all_boards.update(ok2)
        failed = failed2

    # 剩余失败板块冷却后最后补扫一次
    if failed:
        print(f"[cool] retry-wait {RETRY_WAIT}s for {len(failed)} boards: "
              + ",".join(failed), file=sys.stderr, flush=True)
        time.sleep(RETRY_WAIT)
        ok3, perm_failed, _ = run_round_v(failed)
        all_boards.update(ok3)

    payload = {"boards": all_boards, "failed": perm_failed,
               "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
