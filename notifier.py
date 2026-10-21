#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件通知（整合 etf-quant-auto notifier.py + etf-quant 信号邮件模板）
- SMTP 配置全部走环境变量，避免明文入库:
  MAIL_SERVER / MAIL_PORT(默认465) / MAIL_USERNAME / MAIL_PASSWORD / MAIL_TO(默认=USERNAME)
- 未配置 MAIL_SERVER 时静默跳过，不影响主流程
- 生成每日操盘日报（纯文本 + HTML 卡片）
"""
import os
import smtplib
from email.mime.text import MIMEText


def send_email(subject, body, html=False, to=None):
    """发送邮件。返回 True/False。未配置 SMTP 环境变量时直接跳过。"""
    host = os.environ.get("MAIL_SERVER")
    if not host:
        return False
    port = int(os.environ.get("MAIL_PORT", "465"))
    user = os.environ.get("MAIL_USERNAME", "")
    pwd = os.environ.get("MAIL_PASSWORD", "")
    to = to or os.environ.get("MAIL_TO", user)
    if not (user and pwd and to):
        return False

    msg = MIMEText(body, "html" if html else "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            s = smtplib.SMTP(host, port, timeout=20)
            s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
        s.quit()
        return True
    except Exception as e:
        print(f"[notifier] 邮件发送失败: {e}")
        return False


# ===================== 日报构建 =====================

def build_daily_report_text(output):
    """从 trading_data.json 结构生成纯文本日报"""
    m1 = output["module_1_environment"]
    m2 = output["module_2_selection"]
    m4 = output["module_4_exit"]
    s = output["summary"]
    lines = [f"【每日操盘日报】{output['updated'][:10]} {output.get('run_time', '')}", ""]
    lines.append(f"市场环境: {m1['env_cn']} | 建议仓位 {m1['position_ratio']*100:.0f}%")

    if s.get("key_action"):
        lines.append(f"关键行动: {s['key_action']}")

    buys = m2.get("signals", [])
    if buys:
        lines.append("")
        lines.append("🟢 买入信号:")
        for sig in buys[:5]:
            fund = sig["funds"][0] if sig.get("funds") else {}
            lines.append(f"  - {sig.get('label','')} {sig['board']} "
                         f"建议仓位¥{sig.get('position', 0):,} "
                         f"{fund.get('code','')} {fund.get('name','')}")
    else:
        lines.append("今日无买入信号 — 不做也是操作")

    exits = m4.get("exit_signals", [])
    alerts = m4.get("sell_alerts", [])
    pos_alerts = m4.get("position_alerts", [])
    if exits or alerts or pos_alerts:
        lines.append("")
        lines.append("🔴 卖出/风险提醒:")
        for e in exits:
            lines.append(f"  - {e['fund_code']} {e.get('board','')} 盈亏{e.get('pnl_pct',0):+.1f}% {e['reason']}")
        for a in alerts:
            lines.append(f"  - [{a['severity']}] {a['title']}: {a['message']}")
        for a in pos_alerts:
            lines.append(f"  - [{a['severity']}] {a['fund_name']}: {a['message']}")

    fee_cal = m4.get("fee_calendar", [])
    if fee_cal:
        lines.append("")
        lines.append("🔓 费率解锁日历:")
        for c in fee_cal[:5]:
            lines.append(f"  - {c['fund_name']}: 还需持有{c['remaining_days']}天，{c['unlock_date']}免赎回费")

    lines.append("")
    lines.append("数据来源: 东方财富/天天基金/蛋卷 · 仅供研究参考，不构成投资建议")
    return "\n".join(lines)


def build_daily_report_html(output):
    """HTML 卡片版日报（样式对齐 etf-quant 买入信号邮件）"""
    m1 = output["module_1_environment"]
    m2 = output["module_2_selection"]
    m4 = output["module_4_exit"]
    env_color = {"bull": "#22c55e", "bull_lean": "#84cc16", "range": "#f59e0b",
                 "bear_lean": "#f97316", "bear": "#ef4444"}.get(m1["env"], "#9ca3af")

    def cards(items, color, fmt):
        out = ""
        for it in items:
            out += ('<div style="border:1px solid #e6e8ef;border-left:4px solid %s;border-radius:10px;'
                    'padding:12px;margin-bottom:8px;background:#fff;">%s</div>') % (color, fmt(it))
        return out or '<div style="font-size:13px;color:#64748b;">无</div>'

    buys_html = cards(m2.get("signals", [])[:5], "#ef4444",
                      lambda x: '<div style="font-size:14px;font-weight:700;color:#1e293b;">%s %s</div>'
                                '<div style="font-size:12px;color:#64748b;margin-top:4px;">建议仓位 ¥%s · %s %s</div>'
                      % (x.get("label", ""), x["board"], format(x.get("position", 0), ","),
                         (x.get("funds") or [{}])[0].get("code", ""), (x.get("funds") or [{}])[0].get("name", "")))
    exit_items = m4.get("exit_signals", []) + m4.get("sell_alerts", []) + m4.get("position_alerts", [])
    exits_html = cards(exit_items, "#ef4444",
                       lambda x: '<div style="font-size:13px;color:#1e293b;">%s</div>'
                                 '<div style="font-size:12px;color:#64748b;margin-top:3px;">%s</div>'
                       % (x.get("title") or "%s %s" % (x.get("fund_code", ""), x.get("board", "")),
                          x.get("message") or x.get("reason", "")))
    cal_html = cards(m4.get("fee_calendar", [])[:5], "#2563eb",
                     lambda x: '<div style="font-size:13px;color:#1e293b;">%s</div>'
                               '<div style="font-size:12px;color:#64748b;margin-top:3px;">还需持有 %d 天，%s 免赎回费</div>'
                     % (x["fund_name"], x["remaining_days"], x["unlock_date"]))

    return ('<div style="background:#eef1f7;padding:24px;font-family:-apple-system,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;">'
            '<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;">'
            '<div style="background:linear-gradient(135deg,#1e1b4b,#4f46e5);padding:22px;color:#fff;">'
            '<div style="font-size:18px;font-weight:800;">📊 每日操盘日报</div>'
            '<div style="font-size:13px;opacity:.85;margin-top:6px;">%s · 市场: <span style="color:%s;font-weight:700">%s</span> · 建议仓位 %.0f%%</div></div>'
            '<div style="padding:20px 22px;">'
            '<div style="font-size:14px;font-weight:700;margin:6px 0 8px;">🟢 买入信号</div>%s'
            '<div style="font-size:14px;font-weight:700;margin:14px 0 8px;">🔴 卖出 / 风险提醒</div>%s'
            '<div style="font-size:14px;font-weight:700;margin:14px 0 8px;">🔓 费率解锁日历</div>%s'
            '<div style="margin-top:16px;padding:12px;background:#f8fafc;border-radius:10px;font-size:12px;color:#475569;">'
            '关键行动: %s<br>数据来源: 东方财富/天天基金/蛋卷 · 仅供研究参考，不构成投资建议</div>'
            '</div></div></div>') % (
        output["updated"][:10], env_color, m1["env_cn"], m1["position_ratio"] * 100,
        buys_html, exits_html, cal_html, output["summary"].get("key_action", ""))


def notify_daily_report(output):
    """主流程调用入口: 配置了SMTP才发送。返回是否发送成功。"""
    if not os.environ.get("MAIL_SERVER"):
        return False
    day = output["updated"][:10]
    n_buys = output["module_2_selection"]["actionable_signals"]
    n_exits = len(output["module_4_exit"]["exit_signals"]) + len(output["module_4_exit"]["sell_alerts"])
    subject = f"📈 操盘日报 {day} | 买入{n_buys} 卖出/风险{n_exits} | {output['module_1_environment']['env_cn']}"
    ok = send_email(subject, build_daily_report_html(output), html=True)
    if ok:
        print(f"[notifier] 日报已发送: {subject}")
    return ok


if __name__ == "__main__":
    # 本地预览（不发送）: python3 notifier.py [trading_data.json路径]
    import json, sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "trading_data.json")
    with open(path, "r", encoding="utf-8") as f:
        output = json.load(f)
    print(build_daily_report_text(output))
