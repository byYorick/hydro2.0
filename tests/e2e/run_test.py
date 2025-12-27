#!/usr/bin/env python3
"""
Simple E2E test runner script
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Shift arguments - remove "run" command
if len(sys.argv) > 1 and sys.argv[1] == "run":
    sys.argv.pop(1)

from runner.e2e_runner import main

if __name__ == "__main__":
    asyncio.run(main())
