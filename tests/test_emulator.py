"""Integration tests for src/emulator.py."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.emulator import Emulator

# ---------------------------------------------------------------------------
# ROM path helper
# ---------------------------------------------------------------------------

_ROM_PATH: str = str(
    Path(__file__).resolve().parent.parent / "Super Mario Bros. (E) (PRG0) [!].nes"
)

_ROM_AVAILABLE: bool = Path(_ROM_PATH).exists()

_skip_if_no_rom = pytest.mark.skipif(
    not _ROM_AVAILABLE,
    reason="ROM file not available",
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmulatorCreation:
    """Emulator construction tests."""

    @_skip_if_no_rom
    def test_emulator_creation(self) -> None:
        """Verify that all components are created and non-None."""
        emu = Emulator(_ROM_PATH, scale=1)
        assert emu.cpu is not None
        assert emu.ppu is not None
        assert emu.bus is not None
        assert emu.ppu_bus is not None
        assert emu.cartridge is not None
        assert emu.controller is not None
        assert emu.renderer is not None
        emu.stop()

    def test_emulator_invalid_rom(self) -> None:
        """Verify that an invalid ROM file raises an exception."""
        with tempfile.NamedTemporaryFile(suffix=".nes", delete=False) as f:
            f.write(b"INVALID ROM DATA")
            temp_path = f.name

        try:
            with pytest.raises((ValueError, Exception)):
                Emulator(temp_path, scale=1)
        finally:
            os.unlink(temp_path)


class TestEmulatorFrameRun:
    """Tests that exercise ``_run_frame()``."""

    @_skip_if_no_rom
    def test_run_one_frame(self) -> None:
        """Run one frame -- frame_complete should be True afterwards."""
        emu = Emulator(_ROM_PATH, scale=1)
        emu._run_frame()
        assert emu.ppu.frame_complete
        emu.stop()

    @_skip_if_no_rom
    def test_frame_has_visible_content(self) -> None:
        """Run enough frames that the PPU produces visible content."""
        emu = Emulator(_ROM_PATH, scale=1, headless=True)
        # Run enough frames for the ROM to initialise PPU registers
        for _ in range(60):
            emu._run_frame()

        # Frame buffer should contain at least two different colours
        colors = set(emu.ppu.framebuffer)
        assert len(colors) >= 2
        emu.stop()

    @_skip_if_no_rom
    def test_run_multiple_frames(self) -> None:
        """Run 10 consecutive frames without crashing."""
        emu = Emulator(_ROM_PATH, scale=1, headless=True)
        for _ in range(10):
            emu._run_frame()
            assert emu.ppu.frame_complete
        emu.stop()


class TestEmulatorReset:
    """Reset-then-continue tests."""

    @_skip_if_no_rom
    def test_reset(self) -> None:
        """reset() should allow further frames to be run."""
        emu = Emulator(_ROM_PATH, scale=1)
        emu._run_frame()
        emu.reset()
        # After reset, PC should be reloaded from the reset vector (not 0)
        assert emu.cpu.pc != 0
        emu._run_frame()
        emu.stop()


class TestEmulatorInput:
    """Controller input integration tests."""

    @_skip_if_no_rom
    def test_controller_input(self) -> None:
        """Pressing/releasing keys should not crash the emulator."""
        emu = Emulator(_ROM_PATH, scale=1)

        # Press Start
        emu.controller.key_press("Return")
        emu._run_frame()
        emu.controller.key_release("Return")

        # Press a direction
        emu.controller.key_press("Right")
        emu._run_frame()
        emu.controller.key_release("Right")

        emu.stop()


class TestEmulatorFPS:
    """FPS display tests."""

    @_skip_if_no_rom
    def test_fps_display(self) -> None:
        """FPS counter update should not crash."""
        emu = Emulator(_ROM_PATH, scale=1)
        for _ in range(60):
            emu._run_frame()
        emu._update_fps_display()
        emu.stop()
