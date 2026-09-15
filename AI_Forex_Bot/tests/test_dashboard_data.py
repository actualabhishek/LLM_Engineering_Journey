"""
tests/test_dashboard_data.py
------------------------------
Tests for the pure-function loaders in dashboard/data.py (Iteration 3,
Phase 8). Covers the missing-file and malformed-JSON fallback paths, which
are testable without a running Streamlit server or a live MT5 connection.
Full end-to-end rendering is covered by manual smoke testing instead —
Streamlit's testing story doesn't cover this well, and it's a personal-use
dashboard rather than a public product.
"""

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.data import load_json, load_csv, load_trade_history


class TestLoadJson:
    def test_missing_file_returns_default(self, tmp_path):
        result = load_json(tmp_path / "nope.json", default={"a": 1})
        assert result == {"a": 1}

    def test_malformed_json_returns_default(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        result = load_json(bad, default=[])
        assert result == []

    def test_valid_json_loads(self, tmp_path):
        good = tmp_path / "good.json"
        good.write_text(json.dumps({"active": True}))
        result = load_json(good, default={})
        assert result == {"active": True}


class TestLoadCsv:
    def test_missing_file_returns_empty_dataframe(self, tmp_path):
        result = load_csv(tmp_path / "nope.csv")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_valid_csv_loads(self, tmp_path):
        path = tmp_path / "trades.csv"
        path.write_text("pair,profit_usd\nEURUSD,12.5\nGBPUSD,-3.2\n")
        result = load_csv(path)
        assert len(result) == 2
        assert list(result["pair"]) == ["EURUSD", "GBPUSD"]


class TestLoadTradeHistory:
    """load_trade_history() is @st.cache_data-wrapped but still callable
    directly outside a running Streamlit server (caching just falls back to
    an in-memory store with a harmless warning)."""

    def test_missing_file_returns_empty_dataframe(self, monkeypatch, tmp_path):
        import dashboard.data as data_mod
        monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
        result = data_mod.load_trade_history()
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_numeric_columns_coerced_and_dtype_errors_become_nan(self, monkeypatch, tmp_path):
        import dashboard.data as data_mod
        monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
        path = tmp_path / "trade_history.csv"
        path.write_text(
            "pair,profit_usd,pips,confidence,close_time\n"
            "EURUSD,12.5,8.0,77,2026-01-01T00:00:00Z\n"
            "GBPUSD,not_a_number,3.1,80,2026-01-01T01:00:00Z\n"
        )
        df = data_mod.load_trade_history()
        assert df["profit_usd"].iloc[0] == 12.5
        assert pd.isna(df["profit_usd"].iloc[1])
        assert pd.api.types.is_datetime64_any_dtype(df["close_time"])
