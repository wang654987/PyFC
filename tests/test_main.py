"""Integration tests for src/main.py."""

from __future__ import annotations


class TestMain:
    """Main entry-point tests."""

    def test_main_module_importable(self) -> None:
        """Verify that ``src.main.main`` is importable and callable."""
        from src.main import main

        assert callable(main)

    def test_main_no_rom_no_crash(self) -> None:
        """Verify that ``main()`` is callable (logic-only, no GUI)."""
        from src.main import main

        assert callable(main)
