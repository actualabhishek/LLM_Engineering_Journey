"""
daily_summary.py
----------------
End-of-day performance summary generator.
Computes daily/weekly stats from trade_history.csv and ai_logs.json,
writes a human-readable report to logs/daily_reports/, and optionally
sends it via email or webhook.

Run standalone:
    python utils/daily_summary.py

Or import and call generate_daily_summary() from a scheduler.
"""

import csv
import json
import os
import smtplib
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

# ── paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
HISTORY    = BASE_DIR / "storage" / "trade_history.csv"
AI_LOGS    = BASE_DIR / "storage" / "ai_logs.json"
DAILY_STATS = BASE_DIR / "storage" / "daily_stats.json"
REPORT_DIR = BASE_DIR / "storage" / "logs" / "daily_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── helpers ───────────────────────────────────────────────────────────────────

def _load_trades_for_period(days: int = 1) -> list[dict]:
    """Return closed trades from the last `days` calendar days."""
    if not HISTORY.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    trades = []
    with open(HISTORY, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts = datetime.fromisoformat(row.get("close_time", ""))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    trades.append(row)
            except (ValueError, TypeError):
                continue
    return trades


def _load_ai_decisions_for_period(days: int = 1) -> list[dict]:
    """Return AI decision log entries from the last `days` days."""
    if not AI_LOGS.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        with open(AI_LOGS) as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    result = []
    for e in entries:
        try:
            ts = datetime.fromisoformat(e.get("timestamp", ""))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                result.append(e)
        except (ValueError, TypeError):
            continue
    return result


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ── core computation ──────────────────────────────────────────────────────────

def compute_stats(trades: list[dict]) -> dict:
    """Compute core performance metrics from a list of trade dicts."""
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "largest_win": 0.0,
            "largest_loss": 0.0,
            "expectancy": 0.0,
            "by_pair": {},
            "by_session": {},
            "by_direction": {},
        }

    pnls = [_safe_float(t.get("profit_loss")) for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    be     = [p for p in pnls if p == 0]

    total_pnl    = sum(pnls)
    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss else float("inf")

    win_rate = len(wins) / len(pnls) * 100 if pnls else 0.0
    avg_win  = statistics.mean(wins)  if wins   else 0.0
    avg_loss = statistics.mean(losses) if losses else 0.0

    # Expectancy per trade
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    # Break down by pair
    by_pair: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_pair[t.get("symbol", "UNKNOWN")].append(_safe_float(t.get("profit_loss")))

    by_pair_stats = {}
    for pair, plist in by_pair.items():
        p_wins = [p for p in plist if p > 0]
        by_pair_stats[pair] = {
            "trades":   len(plist),
            "net_pnl":  round(sum(plist), 2),
            "win_rate": round(len(p_wins) / len(plist) * 100, 1) if plist else 0,
        }

    # Break down by session
    by_session: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_session[t.get("session", "unknown")].append(_safe_float(t.get("profit_loss")))

    by_session_stats = {
        s: {"trades": len(pl), "net_pnl": round(sum(pl), 2)}
        for s, pl in by_session.items()
    }

    # Break down by direction
    by_dir: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_dir[t.get("direction", "unknown")].append(_safe_float(t.get("profit_loss")))

    by_direction_stats = {
        d: {"trades": len(pl), "net_pnl": round(sum(pl), 2)}
        for d, pl in by_dir.items()
    }

    return {
        "total_trades":   len(trades),
        "wins":           len(wins),
        "losses":         len(losses),
        "breakeven":      len(be),
        "win_rate":       round(win_rate, 2),
        "total_pnl":      round(total_pnl, 2),
        "gross_profit":   round(gross_profit, 2),
        "gross_loss":     round(gross_loss, 2),
        "profit_factor":  round(profit_factor, 3),
        "avg_win":        round(avg_win, 2),
        "avg_loss":       round(avg_loss, 2),
        "largest_win":    round(max(wins, default=0.0), 2),
        "largest_loss":   round(min(losses, default=0.0), 2),
        "expectancy":     round(expectancy, 4),
        "by_pair":        by_pair_stats,
        "by_session":     by_session_stats,
        "by_direction":   by_direction_stats,
    }


def compute_ai_stats(ai_entries: list[dict]) -> dict:
    """Summarise AI engine activity from decision log entries."""
    if not ai_entries:
        return {"total_decisions": 0, "llm_used": 0, "llm_pct": 0.0, "avg_confidence": 0.0, "skipped": 0}

    total     = len(ai_entries)
    llm_used  = sum(1 for e in ai_entries if e.get("llm_used", False))
    skipped   = sum(1 for e in ai_entries if e.get("action") == "SKIP")
    confs     = [_safe_float(e.get("final_confidence")) for e in ai_entries if e.get("final_confidence") is not None]
    avg_conf  = round(statistics.mean(confs), 2) if confs else 0.0

    return {
        "total_decisions": total,
        "llm_used":        llm_used,
        "llm_pct":         round(llm_used / total * 100, 1) if total else 0.0,
        "avg_confidence":  avg_conf,
        "skipped":         skipped,
    }


# ── report formatting ─────────────────────────────────────────────────────────

def _bar(value: float, max_val: float = 100, width: int = 20) -> str:
    """ASCII progress bar."""
    if max_val <= 0:
        return " " * width
    filled = int((value / max_val) * width)
    return "█" * filled + "░" * (width - filled)


def format_text_report(stats: dict, ai_stats: dict, period_label: str, report_date: str) -> str:
    s = stats
    a = ai_stats

    pf_str = f"{s['profit_factor']:.3f}" if s['profit_factor'] != float("inf") else "∞"
    pnl_sign = "+" if s["total_pnl"] >= 0 else ""

    lines = [
        "╔══════════════════════════════════════════════════════════════╗",
        f"║       FOREX AI TRADER — {period_label.upper()} REPORT       ",
        f"║       Generated: {report_date}",
        "╠══════════════════════════════════════════════════════════════╣",
        "║  TRADE PERFORMANCE",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Total Trades    : {s['total_trades']}",
        f"║  Wins            : {s['wins']}  |  Losses: {s['losses']}  |  BE: {s['breakeven']}",
        f"║  Win Rate        : {s['win_rate']}%  {_bar(s['win_rate'])}",
        f"║  Net P&L         : {pnl_sign}{s['total_pnl']:.2f} USD",
        f"║  Gross Profit    : +{s['gross_profit']:.2f}  |  Gross Loss: -{s['gross_loss']:.2f}",
        f"║  Profit Factor   : {pf_str}",
        f"║  Avg Win         : +{s['avg_win']:.2f}  |  Avg Loss: {s['avg_loss']:.2f}",
        f"║  Largest Win     : +{s['largest_win']:.2f}  |  Largest Loss: {s['largest_loss']:.2f}",
        f"║  Expectancy/Trade: {s['expectancy']:.4f} USD",
        "╠══════════════════════════════════════════════════════════════╣",
        "║  AI ENGINE SUMMARY",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Total Decisions : {a['total_decisions']}",
        f"║  LLM Invocations : {a['llm_used']} ({a['llm_pct']}% of decisions)",
        f"║  Avg Confidence  : {a['avg_confidence']}",
        f"║  Signals Skipped : {a['skipped']}",
        "╠══════════════════════════════════════════════════════════════╣",
        "║  PERFORMANCE BY PAIR",
        "╠══════════════════════════════════════════════════════════════╣",
    ]

    if s["by_pair"]:
        for pair, ps in sorted(s["by_pair"].items(), key=lambda x: -x[1]["net_pnl"]):
            sign = "+" if ps["net_pnl"] >= 0 else ""
            lines.append(f"║  {pair:<10}  Trades:{ps['trades']:>3}  WR:{ps['win_rate']:>5}%  P&L:{sign}{ps['net_pnl']:.2f}")
    else:
        lines.append("║  No pair data available.")

    lines += [
        "╠══════════════════════════════════════════════════════════════╣",
        "║  PERFORMANCE BY SESSION",
        "╠══════════════════════════════════════════════════════════════╣",
    ]

    if s["by_session"]:
        for sess, ss in sorted(s["by_session"].items(), key=lambda x: -x[1]["net_pnl"]):
            sign = "+" if ss["net_pnl"] >= 0 else ""
            lines.append(f"║  {sess:<15}  Trades:{ss['trades']:>3}  P&L:{sign}{ss['net_pnl']:.2f}")
    else:
        lines.append("║  No session data available.")

    lines.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)


# ── delivery ──────────────────────────────────────────────────────────────────

def _send_email(subject: str, body: str) -> bool:
    """
    Send report via email if SMTP env vars are set.
    Required env vars:
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, REPORT_EMAIL_TO
    """
    host  = os.getenv("SMTP_HOST")
    port  = int(os.getenv("SMTP_PORT", "587"))
    user  = os.getenv("SMTP_USER")
    pw    = os.getenv("SMTP_PASS")
    to    = os.getenv("REPORT_EMAIL_TO")

    if not all([host, user, pw, to]):
        return False  # SMTP not configured — skip silently

    try:
        msg = MIMEMultipart()
        msg["From"]    = user
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(host, port) as s:
            s.starttls()
            s.login(user, pw)
            s.sendmail(user, to, msg.as_string())
        return True
    except Exception as exc:
        print(f"[DailySummary] Email failed: {exc}")
        return False


def _send_webhook(report_text: str, stats: dict) -> bool:
    """
    POST summary to a custom webhook (e.g. Discord, Slack, Telegram bot)
    if REPORT_WEBHOOK_URL env var is set.
    """
    import urllib.request, urllib.error
    url = os.getenv("REPORT_WEBHOOK_URL")
    if not url:
        return False
    try:
        payload = json.dumps({
            "text":   report_text[:2000],  # Discord 2000-char limit
            "stats":  stats,
            "source": "forex_ai_trader_daily_summary",
        }).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as exc:
        print(f"[DailySummary] Webhook failed: {exc}")
        return False


# ── main public API ───────────────────────────────────────────────────────────

def generate_daily_summary(days: int = 1, send: bool = True) -> dict:
    """
    Generate a performance summary for the last `days` period.

    Args:
        days: Number of calendar days to look back (1 = today, 7 = weekly).
        send: Whether to attempt email/webhook delivery.

    Returns:
        dict with keys 'stats', 'ai_stats', 'report_text', 'report_path'.
    """
    period_label = "daily" if days == 1 else f"{days}-day"
    now          = datetime.now(timezone.utc)
    report_date  = now.strftime("%Y-%m-%d %H:%M UTC")
    filename     = f"report_{now.strftime('%Y%m%d')}_{period_label}.txt"
    report_path  = REPORT_DIR / filename

    trades      = _load_trades_for_period(days)
    ai_entries  = _load_ai_decisions_for_period(days)

    stats    = compute_stats(trades)
    ai_stats = compute_ai_stats(ai_entries)
    report   = format_text_report(stats, ai_stats, period_label, report_date)

    # Write report file
    try:
        report_path.write_text(report, encoding="utf-8")
        print(f"[DailySummary] Report saved → {report_path}")
    except OSError as e:
        print(f"[DailySummary] Failed to write report: {e}")

    # Optional delivery
    if send:
        subject = f"[ForexAI] {period_label.title()} Report — {now.strftime('%Y-%m-%d')} — P&L: {stats['total_pnl']:.2f} USD"
        _send_email(subject, report)
        _send_webhook(report, stats)

    return {
        "stats":       stats,
        "ai_stats":    ai_stats,
        "report_text": report,
        "report_path": str(report_path),
    }


def generate_weekly_summary(send: bool = True) -> dict:
    """Convenience wrapper for a 7-day summary."""
    return generate_daily_summary(days=7, send=send)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate ForexAI performance report")
    parser.add_argument("--days",   type=int, default=1,    help="Look-back window in days (default: 1)")
    parser.add_argument("--no-send", action="store_true",   help="Skip email/webhook delivery")
    args = parser.parse_args()

    result = generate_daily_summary(days=args.days, send=not args.no_send)
    print("\n" + result["report_text"])
