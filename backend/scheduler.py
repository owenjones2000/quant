"""定时任务调度器 - 每N分钟扫描自选股信号，触发通知"""
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from signals.engine import scan_all_signals
from notify.sender import send_feishu, send_email
from config import load_config

scheduler = BackgroundScheduler()
_last_signals = set()  # 去重：同一天同一信号只通知一次


def _is_trading_time() -> bool:
    """判断是否在A股交易时间"""
    now = datetime.datetime.now()
    if now.weekday() >= 5:  # 周末
        return False
    t = now.time()
    morning = datetime.time(9, 30) <= t <= datetime.time(11, 30)
    afternoon = datetime.time(13, 0) <= t <= datetime.time(15, 0)
    return morning or afternoon


def _format_signals(signals: list) -> str:
    """格式化信号为通知文本"""
    lines = []
    for s in signals:
        icon = "🔴" if s["type"] == "sell" else "🟢"
        lines.append(f"{icon} **{s['code']}** {s['signal']} 收盘:{s['close']}")
    return "\n".join(lines)


def _notify(signals: list):
    """发送通知"""
    if not signals:
        return
    cfg = load_config()["notify"]
    text = _format_signals(signals)
    title = f"📊 交易信号 ({len(signals)}条)"

    # 飞书
    if cfg.get("feishu_webhook"):
        try:
            send_feishu(cfg["feishu_webhook"], title, text)
        except Exception as e:
            print(f"飞书通知失败: {e}")

    # 邮件
    email_cfg = cfg.get("email", {})
    if email_cfg.get("user") and email_cfg.get("to"):
        try:
            send_email(email_cfg["smtp_host"], email_cfg["smtp_port"],
                       email_cfg["user"], email_cfg["password"],
                       email_cfg["to"], title, text)
        except Exception as e:
            print(f"邮件通知失败: {e}")


def scan_job():
    """定时扫描任务"""
    if not _is_trading_time():
        return

    global _last_signals
    signals = scan_all_signals()

    # 去重：同一天同一code+signal只通知一次
    today = datetime.date.today().isoformat()
    new_signals = []
    for s in signals:
        key = f"{today}_{s['code']}_{s['signal']}"
        if key not in _last_signals:
            _last_signals.add(key)
            new_signals.append(s)

    if new_signals:
        print(f"[{datetime.datetime.now():%H:%M:%S}] 新信号: {new_signals}")
        _notify(new_signals)
    else:
        print(f"[{datetime.datetime.now():%H:%M:%S}] 扫描完成，无新信号")


def start_scheduler():
    """启动定时扫描"""
    cfg = load_config()
    interval = cfg.get("scan_interval_minutes", 3)
    scheduler.add_job(scan_job, "interval", minutes=interval, id="signal_scan",
                      replace_existing=True)
    scheduler.start()
    print(f"✅ 调度器已启动，每{interval}分钟扫描一次")


def stop_scheduler():
    scheduler.shutdown()
