#!/usr/bin/env python3
"""Convenience wrapper to run the exporter.

Usage:
  python backend/export_stats.py --db data/commander_tracker.sqlite --docs docs
"""
from commander_stats.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
