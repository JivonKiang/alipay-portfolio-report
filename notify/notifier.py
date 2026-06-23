"""
通知模块 - 通过 Marvis 自定义任务推送交易信号
支持：每日定时推送、即时推送、回测报告推送
"""
import os
import json
from datetime import date


class Notifier:
    def __init__(self, output_dir="./output/reports"):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def push_daily_report(self, decisions, report_text):
        """生成每日报告文件（Marvis 后续通过自定义任务读取并推送）"""
        today = date.today().strftime("%Y-%m-%d")
        report_path = os.path.join(self.output_dir, f"daily_report_{today}.md")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
            f.write(f"\n\n---\n*报告由 fund-trend-system 自动生成*")

        # 生成结构化数据供 Marvis 自定义任务读取
        signal_json_path = os.path.join(self.output_dir, f"signals_{today}.json")
        with open(signal_json_path, "w", encoding="utf-8") as f:
            json.dump(decisions, f, ensure_ascii=False, indent=2, default=str)

        return report_path

    def push_alert(self, title, message, level="info"):
        """生成告警文件"""
        today = date.today().strftime("%Y-%m-%d")
        alert_path = os.path.join(self.output_dir, f"alert_{today}.md")

        content = f"## {level.upper()}: {title}\n\n{message}"
        with open(alert_path, "w", encoding="utf-8") as f:
            f.write(content)

        return alert_path

    def push_backtest_report(self, report_df, report_path=None):
        """推送回测报告"""
        if report_path is None:
            today = date.today().strftime("%Y-%m-%d")
            report_path = os.path.join(self.output_dir, f"backtest_report_{today}.md")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("## 策略回测报告\n\n")
            f.write(report_df.to_markdown(index=False))
            f.write(f"\n\n---\n*报告由 fund-trend-system 自动生成*")

        return report_path

    def get_latest_report(self, prefix="daily_report"):
        """获取最新报告内容"""
        files = sorted(
            [f for f in os.listdir(self.output_dir) if f.startswith(prefix)],
            reverse=True,
        )
        if not files:
            return None
        latest = os.path.join(self.output_dir, files[0])
        with open(latest, "r", encoding="utf-8") as f:
            return f.read()
