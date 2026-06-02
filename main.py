"""PyFC - Python NES/Famicom Emulator -- entry-point shim.

Call through to ``src.main.main()`` so that ``python main.py`` works
identically to ``python -m src.main``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that ``src.main`` is importable.
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.main import main  # noqa: E402

if __name__ == "__main__":
    main()
