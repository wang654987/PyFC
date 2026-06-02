"""PyFC Emulator -- main controller that wires all modules together.

Orchestrates the CPU to PPU main loop, frame-rate limiting, and
communication between every subsystem of the NES emulator.
"""

from __future__ import annotations

import time
from pathlib import Path

from .bus import Bus
from .cartridge import Cartridge
from .cpu import CPU6502
from .input import Controller
from .ppu import PPU
from .ppu_bus import PPUBus
from .renderer import Renderer


class Emulator:
    """FC/NES emulator main controller.

    Responsibilities:
    1. Create and wire all subsystems
    2. Drive the main loop (CPU -> PPU -> render)
    3. Frame-rate control (target 60 FPS)
    """

    # NTSC clock parameters
    CPU_CLOCK: int = 1_789_773   # CPU master clock (Hz)
    PPU_CLOCK: int = 5_369_319   # PPU master clock (CPU x 3)
    FPS: float = 30.0            # Target frame rate
    CYCLES_PER_FRAME: int = 29_781  # CPU cycles per frame
    FRAME_TIME: float = 1.0 / 30.0  # Target duration per frame (s)

    def __init__(
        self, rom_path: str, scale: int = 3, *, headless: bool = False
    ) -> None:
        """Initialise the emulator.

        Args:
            rom_path: Path to a .nes ROM file.
            scale: Screen zoom multiplier.
            headless: Skip creating a renderer window (for tests/CI).

        """
        # ---- Step 1: load ROM ---------------------------------------
        rom_bytes = Path(rom_path).read_bytes()
        self.cartridge = Cartridge(rom_bytes)

        # ---- Step 2: create input device ----------------------------
        self.controller = Controller()

        # ---- Step 3: create PPU & PPUBus ----------------------------
        self.ppu_bus = PPUBus(
            cartridge=self.cartridge,
            mirror_mode=self.cartridge.mirror_mode,
        )
        self.ppu = PPU(self.ppu_bus)

        # ---- Step 4: create CPU & Bus -------------------------------
        self.bus = Bus(
            ppu=self.ppu,
            cartridge=self.cartridge,
            controller=self.controller,
        )
        self.cpu = CPU6502(self.bus)

        # ---- Step 5: wire PPU NMI callback -> CPU -------------------
        self.ppu.nmi_callback = self.cpu.nmi
        # CPU IRQ is not implemented yet (Mapper 0 has no IRQ source)

        # ---- Step 6: create renderer ---------------------------------
        self._headless = headless
        rom_name = Path(rom_path).name
        self._base_title = f"PyFC - {rom_name}"

        if headless:
            self.renderer = None
        else:
            self.renderer = Renderer(title=self._base_title, scale=scale)
            self.renderer.bind_input(self.controller)

        # ---- Step 7: reset all subsystems ---------------------------
        self.cpu.reset()
        self.ppu.reset()

        # ---- Frame-rate control ------------------------------------
        self._running = False
        self._frame_count = 0
        self._fps_update_time = time.monotonic()
        self._last_frame_time = time.monotonic()

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the emulator.

        Uses ``after()``-style frame scheduling instead of a synchronous
        ``while`` loop so that the window event loop remains responsive.
        """
        if self._headless:
            self._run_headless()
            return

        self._running = True
        self._last_frame_time = time.monotonic()
        self._schedule_next_frame()
        self.renderer.start()  # type: ignore[union-attr]

    def _schedule_next_frame(self) -> None:
        """Schedule the next frame callback via the renderer."""
        if not self._running:
            return
        if self.renderer is not None:
            self.renderer.schedule(1, self._frame_loop)

    def _frame_loop(self) -> None:
        """Frame callback -- driven by the renderer's timer.

        Each invocation:
        1. Runs CPU instructions until the PPU completes one frame
        2. Renders the frame buffer to the window
        3. Re-schedules itself for the next frame

        Frame-rate limiting is enforced by checking the wall-clock
        interval against ``FRAME_TIME``.
        """
        if not self._running:
            return

        current_time = time.monotonic()
        elapsed = current_time - self._last_frame_time

        # Frame-rate control: no faster than FRAME_TIME
        if elapsed >= self.FRAME_TIME:
            self._run_frame()
            if self.renderer is not None:
                self.renderer.render_frame(self.ppu.framebuffer)
            self._last_frame_time = current_time
            self._update_fps_display()

        self._schedule_next_frame()

    def _run_headless(self) -> None:
        """Run emulation frames without a render window (for tests/benchmarks)."""
        self._running = True
        try:
            while self._running:
                self._run_frame()
                self._frame_count += 1
        except KeyboardInterrupt:
            pass
        self._running = False

    def _run_frame(self) -> None:
        """Execute one frame's worth of CPU/PPU simulation.

        Loops until ``PPU.frame_complete`` is True, advancing the CPU by
        one instruction and then ticking the PPU in batch via
        ``tick_batch()`` — which avoids the per-cycle Python call overhead
        of the old ``for _ in range(c): ppu.tick()`` pattern and
        fast-forwards through VBlank automatically.

        A safety cap prevents infinite hangs caused by buggy ROMs.
        """
        ppu = self.ppu
        cpu = self.cpu
        ppu.frame_complete = False
        frame_cycles = 0
        max_cycles = self.CYCLES_PER_FRAME * 2  # safety ceiling

        # Cache method references to avoid repeated attribute lookups
        cpu_step = cpu.step
        ppu_tick_batch = ppu.tick_batch

        while not ppu.frame_complete:
            if frame_cycles > max_cycles:
                break
            cpu_cycles = cpu_step()
            frame_cycles += cpu_cycles
            ppu_tick_batch(cpu_cycles * 3)


    def _update_fps_display(self) -> None:
        """Update the window title with the current FPS once per second."""
        self._frame_count += 1
        now = time.monotonic()
        elapsed = now - self._fps_update_time

        if elapsed >= 1.0:
            fps = self._frame_count / elapsed
            if self.renderer is not None:
                self.renderer.set_title(f"{self._base_title} - {fps:.1f} FPS")
            self._frame_count = 0
            self._fps_update_time = now

    def reset(self) -> None:
        """Reset all subsystems (CPU, PPU, Controller) to initial state."""
        self.cpu.reset()
        self.ppu.reset()
        self.controller.reset()
        self._frame_count = 0
        self._last_frame_time = time.monotonic()
        self._fps_update_time = time.monotonic()

    def stop(self) -> None:
        """Stop the emulator and destroy the render window."""
        self._running = False
        if self.renderer is not None:
            self.renderer.stop()
