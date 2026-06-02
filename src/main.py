"""PyFC - Python NES/Famicom Emulator.

Usage::

    python -m src.main [ROM_PATH]

Default ROM: ``Super Mario Bros. (E) (PRG0) [!].nes`` in the project root.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    """Program entry point."""
    if len(sys.argv) > 1:
        rom_path = sys.argv[1]
    else:
        # Default ROM path
        project_root = Path(__file__).resolve().parent.parent
        default_rom = project_root / "Super Mario Bros. (E) (PRG0) [!].nes"
        if not default_rom.exists():
            print(
                "Error: default ROM file not found.\n"
                "  Place the ROM in the project root or specify it:\n"
                "  python -m src.main <rom_path>"
            )
            sys.exit(1)
        rom_path = str(default_rom)

    print(f"Loading ROM: {rom_path}")
    print(
        "Controls: WASD/Arrows=Move  J/Z=A  K/X=B  "
        "Enter=Start  RightShift=Select"
    )
    print("Window size: 768x720 (3x)")
    print()

    from .emulator import Emulator

    emulator = Emulator(rom_path, scale=3)

    try:
        emulator.run()
    except KeyboardInterrupt:
        print("\nEmulator exited.")
    except Exception as exc:
        print(f"Error: {exc}")
        emulator.stop()
        raise


if __name__ == "__main__":
    main()
