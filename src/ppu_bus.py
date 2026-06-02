"""PPU bus — routes PPU-side reads/writes to CHR-ROM and Nametable RAM.

Manages the PPU's 14-bit address space (``$0000-$3FFF``).  Like ``Bus``,
this is a pure address decoder with devices injected through the constructor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cartridge import Cartridge

# Mirror-mode constants (match the iNES header convention)
HORIZONTAL: int = 0
VERTICAL: int = 1


class PPUBus:
    """PPU address-space bus.

    Handles:
    - CHR-ROM reads/writes (``$0000-$1FFF``, delegated to Cartridge)
    - Nametable reads/writes (``$2000-$3EFF``, with mirroring)
    - Palette area (``$3F00-$3FFF``) returns 0 — the PPU manages it internally
    """

    def __init__(
        self,
        cartridge: Cartridge | None = None,
        mirror_mode: int = HORIZONTAL,
    ) -> None:
        """Create a PPUBus.

        Args:
            cartridge: Cartridge instance for CHR-ROM access (can be *None*).
            mirror_mode: Nametable mirroring mode — ``HORIZONTAL`` (0) or
                ``VERTICAL`` (1).  Defaults to ``HORIZONTAL``.

        """
        self.cartridge: Cartridge | None = cartridge
        self.nametable: bytearray = bytearray(2048)  # 2 KB
        self.mirror_mode: int = mirror_mode

    # ------------------------------------------------------------------
    # read
    # ------------------------------------------------------------------

    def read(self, address: int) -> int:
        """Read a byte from the PPU address space.

        - ``$0000-$1FFF`` → CHR-ROM (via Cartridge)
        - ``$2000-$3EFF`` → Nametable (with mirroring)
        - ``$3F00-$3FFF`` → Palette (returns 0 — managed by PPU internally)
        """
        address &= 0x3FFF  # 14-bit address space

        if address < 0x2000:
            if self.cartridge is not None:
                return self.cartridge.ppu_read(address)
            return 0

        if address < 0x3F00:
            return self.nametable[self._mirror_address(address)]

        # Palette area — PPU manages this internally
        return 0

    # ------------------------------------------------------------------
    # write
    # ------------------------------------------------------------------

    def write(self, address: int, value: int) -> None:
        """Write *value* to the PPU address space.

        - ``$0000-$1FFF`` → CHR-ROM (usually read-only; CHR-RAM supports writes)
        - ``$2000-$3EFF`` → Nametable write
        - ``$3F00-$3FFF`` → Palette (ignored — PPU manages it internally)
        """
        address &= 0x3FFF
        value &= 0xFF

        if address < 0x2000:
            if self.cartridge is not None:
                self.cartridge.ppu_write(address, value)
            return

        if address < 0x3F00:
            self.nametable[self._mirror_address(address)] = value
            return

        # Palette area — PPU manages this internally, not routed here

    # ------------------------------------------------------------------
    # Nametable mirroring
    # ------------------------------------------------------------------

    def _mirror_address(self, address: int) -> int:
        """Mirror a Nametable-area address to the physical 2 KB buffer.

        The region ``$2000-$3EFF`` contains 4 logical Nametable pages
        (``$2000``, ``$2400``, ``$2800``, ``$2C00``), each 1024 bytes.
        Depending on the mirroring mode, these are folded into 2 physical
        pages (0 or 1).

        **Horizontal mirroring** (default)::

            table 0 ($2000) → physical 0
            table 1 ($2400) → physical 0
            table 2 ($2800) → physical 1
            table 3 ($2C00) → physical 1

        **Vertical mirroring**::

            table 0 ($2000) → physical 0
            table 1 ($2400) → physical 1
            table 2 ($2800) → physical 0
            table 3 ($2C00) → physical 1
        """
        addr: int = (address - 0x2000) & 0x0FFF  # 0..0xFFF
        table: int = addr // 0x0400  # logical table 0-3
        offset: int = addr % 0x0400  # offset within the table

        if self.mirror_mode == VERTICAL:
            table &= 1  # 0→0, 1→1, 2→0, 3→1
        else:
            # HORIZONTAL (and fallback for any other value)
            table = (table >> 1) & 1  # 0→0, 1→0, 2→1, 3→1

        return table * 0x0400 + offset
