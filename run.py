#!/usr/bin/env python3
"""从仓库根目录启动新 CLI：python run.py import --clear"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sichuan_qa.cli import main

if __name__ == "__main__":
    main()
