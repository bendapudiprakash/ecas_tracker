#!/usr/bin/env python3
"""
Root Launcher for CAS Tracker Engine
------------------------------------
Executes tracker_engine/main.py cleanly.
"""

import sys
import os

# Add root directory to sys.path so tracker_engine is importable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from tracker_engine.main import run_all

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run complete eCAS portfolio tracking pipeline.")
    parser.add_argument("--sync", "-s", action="store_true", help="Sync Gmail for new eCAS statements incrementally.")
    parser.add_argument("--force-all", action="store_true", help="Force search entire Gmail mailbox history.")
    parser.add_argument("--ai", "-a", action="store_true", help="Run AI portfolio insights analysis.")
    args = parser.parse_args()

    run_all(sync=args.sync, force_all=args.force_all, with_ai=args.ai)
