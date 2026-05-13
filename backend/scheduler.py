"""定时任务调度器
- 盘中: 每N分钟扫描自选股信号
- 收盘后: 每日选股管道(扫描突破+踢出不合格)
"""
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from signals.engine import scan_all_signals
from tdx_parser.daily_scanner import daily_pipeline
from notify.sender import send_feishu, send_email
from config import load_config

scheduler = BackgroundScheduler()
_last_signals = set()


def _is_trading_time() -> bool:
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (datetime.time(9, 30) <= t <= datetime.time(11, 30) or
            datetime.time(13, 0) <= t <= datetime.time(15, 0))


def _is_after_close() -> bool:
    """收盘后15:05~16:00"""
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return datetime.time(15, 5) <= t <= datetime.time(16, 0)


def _notify(title: str, text: str):
    cfg = load_config()["notify"]
    if cfg.get("feishu_webhook"):
        try:
            send_feishu(cfg["feishu_webhook"], title, text)
        except Exception as e:
            print(f"飞书通知失败: {e}")
    email_cfg = cfg.get("email", {})
    if email_cfg.get("user") and email_cfg.get("to"):
        try:
            send_email(email_cfg["smtp_host"], email_cfg["smtp_port"],
                       email_cfg["user"], email_cfg["password"],
                       email_cfg["to"], title, text)
        except Exception as e:
            print(f"邮件通知失败: {e}")


def scan_job():
    """盘中信号扫描"""
    now = datetime.datetime.now()
    t = now.time()
    # 双重保险：cron 已限制时间段，这里再检查一次
    if not (datetime.time(9, 30) <= t <= datetime.time(11, 30) or
            datetime.time(13, 0) <= t <= datetime.time(15, 0)):
        return
    if now.weekday() >= 5:
        return

    global _last_signals
    signals = scan_all_signals()
    today = datetime.date.today().isoformat()
    new_signals = []
    for s in signals:
        key = f"{today}_{s['code']}_{s['signal']}"
        if key not in _last_signals:
            _last_signals.add(key)
            new_signals.append(s)

    if new_signals:
        print(f"[{datetime.datetime.now():%H:%M:%S}] 新信号: {len(new_signals)}条")
        lines = []
        for s in new_signals:
            icon = "🔴" if s["type"] == "sell" else "🟢"
            lines.append(f"{icon} **{s['code']}** {s['signal']} 收盘:{s['close']}")
        _notify(f"📊 交易信号 ({len(new_signals)}条)", "\n".join(lines))
    else:
        print(f"[{datetime.datetime.now():%H:%M:%S}] 扫描完成，无新信号")


def daily_scan_job():
    """收盘后每日选股管道"""
    print(f"[{datetime.datetime.now():%H:%M:%S}] 开始每日选股管道...")
    result = daily_pipeline()

    # 通知
    lines = []
    if result["picks"]:
        lines.append("**🆕 新入选股票:**")
        for p in result["picks"]:
            tag = "🔥涨停" if p["is_limit_up"] else "📈突破"
            lines.append(f"  {tag} {p['code']} 涨{p['change_pct']}% 压力位:{p['pressure']}")
    if result["kicked_out"]:
        lines.append(f"\n**❌ 踢出:** {', '.join(result['kicked_out'])}")
    lines.append(f"\n自选股总数: {result['watchlist_count']}")

    if result["picks"] or result["kicked_out"]:
        _notify("📋 每日选股报告", "\n".join(lines))


def start_scheduler():
    cfg = load_config()
    interval = cfg.get("scan_interval_minutes", 3)

    # 盘中信号扫描 - 只在交易时间段内触发（避免非交易时间无意义唤醒）
    # 上午 9:30-11:30
    scheduler.add_job(scan_job, "cron",
                      day_of_week="mon-fri",
                      hour="9-11", minute=f"*/{interval}",
                      id="signal_scan_am", replace_existing=True,
                      misfire_grace_time=120)
    # 下午 13:00-15:00
    scheduler.add_job(scan_job, "cron",
                      day_of_week="mon-fri",
                      hour="13-14", minute=f"*/{interval}",
                      id="signal_scan_pm", replace_existing=True,
                      misfire_grace_time=120)

    # 收盘后每日选股 (15:10执行) - 增大 misfire_grace_time 防止睡眠错过
    scheduler.add_job(daily_scan_job, "cron", hour=15, minute=10,
                      day_of_week="mon-fri",
                      id="daily_scan", replace_existing=True,
                      misfire_grace_time=3600)  # 1小时内唤醒仍执行

    scheduler.start()
    print(f"✅ 调度器已启动: 盘中每{interval}分钟扫描信号(仅交易时间), 15:10运行每日选股")


def stop_scheduler():
    scheduler.shutdown()
