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
    if not _is_trading_time():
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

    # 盘中信号扫描
    scheduler.add_job(scan_job, "interval", minutes=interval,
                      id="signal_scan", replace_existing=True)

    # 收盘后每日选股 (15:10执行)
    scheduler.add_job(daily_scan_job, "cron", hour=15, minute=10,
                      day_of_week="mon-fri",
                      id="daily_scan", replace_existing=True)

    scheduler.start()
    print(f"✅ 调度器已启动: 盘中每{interval}分钟扫描信号, 15:10运行每日选股")


def stop_scheduler():
    scheduler.shutdown()
