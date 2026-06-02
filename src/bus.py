"""CPU bus — routes reads/writes to the correct hardware device.

Manages the CPU's 64 KB address space.  Bus is a pure address decoder; it
holds no device state beyond RAM and delegates every access to an injected
device (PPU, Cartridge, Controller).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cartridge import Cartridge
    from .input import Controller
    from .ppu import PPU


class Bus:
    """CPU address-space bus (64 KB addressable).

    Every external device is injected through the constructor so that the
    class can be tested with Mock objects (no real PPU/Cartridge needed).
    """

    def __init__(
        self,
        ram: bytearray | None = None,
        ppu: PPU | None = None,
        cartridge: Cartridge | None = None,
        controller: Controller | None = None,
    ) -> None:
        """Create a Bus.

        Args:
            ram: 2 KB internal RAM (bytearray). If *None*, a blank 2 KB
                bytearray is allocated.
            ppu: PPU instance for register reads/writes (can be *None*).
            cartridge: Cartridge instance for PRG-ROM reads/writes (can be *None*).
            controller: Controller instance for joypad reads/writes (can be *None*).

        """
        self.ram: bytearray = ram if ram is not None else bytearray(2048)
        self.ppu: PPU | None = ppu
        self.cartridge: Cartridge | None = cartridge
        self.controller: Controller | None = controller

    # ------------------------------------------------------------------
    # read
    # ------------------------------------------------------------------

    def read(self, address: int) -> int:
        """Read a byte from *address*.

        Address decoding uses the upper byte for fast-path dispatch:
        - 0x00-0x1F → RAM
        - 0x20-0x3F → PPU registers
        - 0x40-0xFF → Cartridge / APU / Controller
        """
        address &= 0xFFFF                 # ensure 16-bit
        top = address >> 8                # upper byte for fast dispatch

        if top < 0x20:                     # $0000-$1FFF: RAM
            return self.ram[address & 0x07FF]

        if top < 0x40:                     # $2000-$3FFF: PPU
            if self.ppu is not None:
                return self.ppu.cpu_read(0x2000 + (address & 0x07))
            return 0

        if address == 0x4016:              # Controller 1
            if self.controller is not None:
                return self.controller.read()
            return 0

        if address >= 0x4020:              # Cartridge PRG-ROM
            if self.cartridge is not None:
                return self.cartridge.cpu_read(address)
            return 0

        # APU / test registers / controller 2
        return 0

    # ------------------------------------------------------------------
    # write
    # ------------------------------------------------------------------

    def write(self, address: int, value: int) -> None:
        """Write *value* to *address*."""
        address &= 0xFFFF
        top = address >> 8
        value &= 0xFF

        if top < 0x20:                     # $0000-$1FFF: RAM
            self.ram[address & 0x07FF] = value
            return

        if top < 0x40:                     # $2000-$3FFF: PPU
            if self.ppu is not None:
                self.ppu.cpu_write(0x2000 + (address & 0x07), value)
            return

        if address == 0x4014:              # OAM DMA
            if self.ppu is not None:
                base = value << 8
                for i in range(256):
                    self.ppu.oam_write(i, self.read(base + i))
            return

        if address == 0x4016:              # Controller strobe
            if self.controller is not None:
                self.controller.write(value)
            return

        if address >= 0x4020:              # Cartridge
            if self.cartridge is not None:
                self.cartridge.cpu_write(address, value)
            return
