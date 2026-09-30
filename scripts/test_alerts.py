"""Fires one test alert on every configured channel plus a healthchecks.io heartbeat.

Run: python scripts/test_alerts.py
Requires .env filled in (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CALLMEBOT_TG_USER,
CALLMEBOT_WA_PHONE, CALLMEBOT_WA_APIKEY, NTFY_TOPIC, HEALTHCHECKS_PING_URL).
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.alerts.base import Alert  # noqa: E402
from app.alerts.callmebot import CallMeBotCallNotifier, CallMeBotWhatsAppNotifier  # noqa: E402
from app.alerts.ntfy import NtfyNotifier  # noqa: E402
from app.alerts.telegram import TelegramNotifier  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.heartbeat import send_heartbeat  # noqa: E402


async def main() -> None:
    settings = load_settings()
    secrets = settings.secrets

    alert = Alert(
        target_id="test",
        hostname="TEST-ALERT",
        ip="0.0.0.0",
        new_state="DOWN",
        ts=time.time(),
        severity="WARNING",
        rtt_avg=1.0,
        loss_pct=0.0,
    )

    notifiers = {
        "telegram": TelegramNotifier(secrets.telegram_bot_token, secrets.telegram_chat_id),
        "telegram_call": CallMeBotCallNotifier(secrets.callmebot_tg_user),
        "whatsapp": CallMeBotWhatsAppNotifier(secrets.callmebot_wa_phone, secrets.callmebot_wa_apikey),
        "ntfy": NtfyNotifier(secrets.ntfy_topic),
    }

    results: dict[str, bool] = {}
    for name, notifier in notifiers.items():
        results[name] = await notifier.send(alert)

    results["healthchecks"] = await send_heartbeat(secrets.healthchecks_ping_url)

    print("\nTest alert results:")
    ok_count = 0
    for name, ok in results.items():
        print(f"  {name:<14} {'OK' if ok else 'FAILED / not configured'}")
        ok_count += ok

    if ok_count == 0:
        print("\nNothing is configured yet - fill in .env with your Telegram/CallMeBot/ntfy/healthchecks.io secrets.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
