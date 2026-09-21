#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_cli.py - 1-command Launcher for CapCut Cloud High-Throughput Batch Automation CLI
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cli.batch_runner import run_cli_entry

if __name__ == "__main__":
    run_cli_entry()
