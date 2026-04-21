"""通知服务 - 飞书Webhook + 邮件"""
import json
import requests
import smtplib
from email.mime.text import MIMEText

# ---- 飞书 ----
def send_feishu(webhook_url: str, title: str, content: str):
    """飞书机器人通知"""
    msg = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [{"tag": "markdown", "content": content}],
        },
    }
    r = requests.post(webhook_url, json=msg, timeout=10)
    return r.json()


# ---- 邮件 ----
def send_email(smtp_host: str, smtp_port: int, user: str, password: str,
               to_addr: str, subject: str, body: str):
    """SMTP邮件通知"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    with smtplib.SMTP_SSL(smtp_host, smtp_port) as s:
        s.login(user, password)
        s.sendmail(user, [to_addr], msg.as_string())
