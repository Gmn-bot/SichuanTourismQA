#!/usr/bin/env python3
# coding: utf-8
"""GraphRAG CLI 入口。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sichuan_qa.cli import main

if __name__ == "__main__":
    main()
