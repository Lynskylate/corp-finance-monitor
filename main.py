#!/usr/bin/env python3
"""corp-finance-monitor CLI entry point"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from corp_finance_monitor.cli.main import main

if __name__ == "__main__":
    main()
