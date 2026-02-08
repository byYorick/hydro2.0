"""
Общий тестовый bootstrap для каталога tests/.

Гарантирует, что корень automation-engine доступен в sys.path,
чтобы импорты вида `from main import ...` и `from common...` были
стабильны при запуске отдельных файлов и всего набора тестов.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR_STR = str(ROOT_DIR)

if ROOT_DIR_STR not in sys.path:
    sys.path.insert(0, ROOT_DIR_STR)
