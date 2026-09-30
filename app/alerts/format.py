"""Shared alert message formatting. Short enough for a phone lock screen (CLAUDE.md rule 8)."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.alerts.base import Alert

IST = ZoneInfo("Asia/Kolkata")


def format_message(alert: Alert) -> str:
    when = datetime.fromtimestamp(alert.ts, tz=IST).strftime("%d-%b %H:%M IST")
    lines = [f"[{alert.severity}] {alert.hostname} ({alert.ip}) is {alert.new_state}", when]

    if alert.new_state == "UP" and alert.outage_duration_s is not None:
        lines.append(f"was down for {_format_duration(alert.outage_duration_s)}")
    elif alert.rtt_avg is not None or alert.loss_pct is not None:
        rtt = f"{alert.rtt_avg:.0f}ms" if alert.rtt_avg is not None else "n/a"
        loss = f"{alert.loss_pct:.0f}%" if alert.loss_pct is not None else "n/a"
        lines.append(f"rtt={rtt} loss={loss}")

    return "\n".join(lines)


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
