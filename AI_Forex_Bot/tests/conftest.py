"""
conftest.py — pytest configuration for ForexAI Trader test suite.
Ensures the project root is on sys.path for all tests.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
