"""
utils/webhook_examples.py
--------------------------
Example webhook payloads and test utilities.

Copy-paste these into TradingView alert message boxes,
or use the test functions to simulate signals.
"""

import json
import requests
from datetime import datetime, timezone


# ============================================================
# EXAMPLE WEBHOOK PAYLOADS
# (Paste into TradingView Alert → Message box)
# ============================================================

EXAMPLE_BUY_PAYLOAD = {
    "symbol": "EURUSD",
    "timeframe": "15",
    "signal": "BUY",
    "confidence": 72.5,
    "trend": "UPTREND",
    "sl": 1.09500,
    "tp": 1.10250,
    "atr": 0.00085,
    "rsi": 54.3,
    "adx": 28.1,
    "macd_hist": 0.000123,
    "timestamp": "2024-01-15T10:30:00Z"
}

EXAMPLE_SELL_PAYLOAD = {
    "symbol": "GBPUSD",
    "timeframe": "15",
    "signal": "SELL",
    "confidence": 68.0,
    "trend": "DOWNTREND",
    "sl": 1.27500,
    "tp": 1.26000,
    "atr": 0.00120,
    "rsi": 42.1,
    "adx": 31.5,
    "macd_hist": -0.000234,
    "timestamp": "2024-01-15T14:15:00Z"
}

EXAMPLE_CLOSE_PAYLOAD = {
    "symbol": "EURUSD",
    "timeframe": "15",
    "signal": "CLOSE",
    "timestamp": "2024-01-15T16:00:00Z"
}

# ============================================================
# TRADINGVIEW ALERT MESSAGE TEMPLATES
# (Replace values with Pine Script variables in TradingView)
# ============================================================

TV_BUY_MESSAGE = '''
{
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "signal": "BUY",
  "confidence": 75,
  "trend": "UPTREND",
  "timestamp": "{{timenow}}"
}
'''

TV_SELL_MESSAGE = '''
{
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "signal": "SELL",
  "confidence": 75,
  "trend": "DOWNTREND",
  "timestamp": "{{timenow}}"
}
'''

TV_CLOSE_MESSAGE = '''
{
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "signal": "CLOSE",
  "timestamp": "{{timenow}}"
}
'''


# ============================================================
# TEST FUNCTIONS
# ============================================================

def send_test_signal(
    webhook_url: str,
    secret_token: str,
    payload: dict = None,
    signal_type: str = "BUY",
):
    """
    Send a test signal to your webhook server.
    
    Usage:
      send_test_signal(
          webhook_url="http://localhost:8000/webhook",
          secret_token="your_secret",
          signal_type="BUY"
      )
    """
    if payload is None:
        payload = EXAMPLE_BUY_PAYLOAD if signal_type == "BUY" else EXAMPLE_SELL_PAYLOAD
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()

    response = requests.post(
        webhook_url,
        json=payload,
        headers={"X-TV-Token": secret_token, "Content-Type": "application/json"},
        timeout=10,
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response


def send_kill_switch(webhook_url: str, secret_token: str, active: bool = True):
    """Toggle kill switch via API."""
    response = requests.post(
        webhook_url.replace("/webhook", "/kill-switch"),
        json={"active": active, "reason": "Test kill switch"},
        headers={"X-Admin-Token": secret_token},
        timeout=10,
    )
    print(f"Kill switch {'ACTIVATED' if active else 'DEACTIVATED'}: {response.json()}")


if __name__ == "__main__":
    # Test locally
    send_test_signal(
        webhook_url="http://localhost:8000/webhook",
        secret_token="CHANGE_THIS_SECRET_TOKEN",
        signal_type="BUY",
    )
