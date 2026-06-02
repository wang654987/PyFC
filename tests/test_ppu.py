"""Unit tests for PPU using MockPPUBus (dict-backed stub).

Covers:
- Register read/write  ($2000-$2007)
- Two-write latch     ($2005 / $2006)
- VBlank / NMI timing
- Background rendering
- Sprite rendering (8×8, 8×16, flip, priority, transparency)
- Sprite-0 collision
- Frame buffer
"""

from __future__ import annotations

import pytest

from src.ppu import PPU

# ------------------------------------------------------------------
#  Mock PPUBus — dictionary-backed memory for unit tests
# ------------------------------------------------------------------

class MockPPUBus:
    """Dictionary-backed PPUBus for PPU unit testing.

    Memory map:
        0x0000-0x1FFF  CHR-ROM
        0x2000-0x3EFF  Nametable + Attribute tables
        0x3F00-0x3FFF  returned but palette is handled internally
    """

    def __init__(self) -> None:
        """Create an empty MockPPUBus."""
        self.memory: dict[int, int] = {}

    def read(self, address: int) -> int:
        """Read a byte from *address*, returning 0 for unmapped locations."""
        return self.memory.get(address & 0x3FFF, 0)

    def write(self, address: int, value: int) -> None:
        """Write *value* to *address*."""
        self.memory[address & 0x3FFF] = value & 0xFF

    # --- helpers for test setup ---

    def load_chr(self, offset: int, data: list[int]) -> None:
        """Load tile pattern bytes starting at *offset* in CHR-ROM space."""
        for i, b in enumerate(data):
            self.memory[(offset + i) & 0x3FFF] = b & 0xFF

    def write_nametable(self, addr: int, data: list[int]) -> None:
        """Write a sequence of bytes to nametable space (0x2000+)."""
        for i, b in enumerate(data):
            self.memory[(addr + i) & 0x3FFF] = b & 0xFF


# ------------------------------------------------------------------
#  Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def bus() -> MockPPUBus:
    """Return a fresh MockPPUBus."""
    return MockPPUBus()


@pytest.fixture
def ppu(bus: MockPPUBus) -> PPU:
    """Return a fresh PPU wired to a MockPPUBus."""
    return PPU(bus)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════
#  Register tests
# ═══════════════════════════════════════════════════════════════════

class TestRegisters:
    """Tests for the 8 CPU-facing PPU registers ($2000-$2007)."""

    # ---- $2000  PPUCTRL ----

    def test_ppuctrl_write(self, ppu: PPU) -> None:
        """Write $2000 updates ctrl register."""
        ppu.cpu_write(0x2000, 0b10101010)
        assert ppu.ctrl == 0b10101010

    def test_ppuctrl_nmi_enable_bit(self, ppu: PPU) -> None:
        """PPUCTRL bit 7 controls NMI generation."""
        ppu.cpu_write(0x2000, 0x00)  # NMI disabled
        assert (ppu.ctrl & 0x80) == 0

        ppu.cpu_write(0x2000, 0x80)  # NMI enabled
        assert (ppu.ctrl & 0x80) != 0

    # ---- $2001  PPUMASK ----

    def test_ppumask_write(self, ppu: PPU) -> None:
        """Write $2001 updates mask register."""
        ppu.cpu_write(0x2001, 0b01010101)
        assert ppu.mask == 0b01010101

    def test_ppumask_background_disable(self, ppu: PPU) -> None:
        """PPUMASK bit 3 controls background visibility."""
        ppu.cpu_write(0x2001, 0x00)  # all rendering off
        assert (ppu.mask & 0x08) == 0
        ppu.cpu_write(0x2001, 0x08)  # background on
        assert (ppu.mask & 0x08) != 0

    # ---- $2002  PPUSTATUS ----

    def test_ppustatus_read_clears_vblank(self, ppu: PPU) -> None:
        """Reading $2002 clears the VBlank flag (bit 7)."""
        ppu.status = 0x80  # VBlank set
        ppu.cpu_read(0x2002)
        assert (ppu.status & 0x80) == 0

    def test_ppustatus_read_resets_latch(self, ppu: PPU) -> None:
        """Reading $2002 resets the two-write latch."""
        ppu._write_latch = True
        ppu.cpu_read(0x2002)
        assert ppu._write_latch is False

    def test_ppustatus_read_retains_low_bits(self, ppu: PPU) -> None:
        """Reading $2002 returns status | (status & 0x1F) for bus noise."""
        ppu.status = 0x83  # VBlank + bits 0 and 1 set
        result = ppu.cpu_read(0x2002)
        # After read, vblank is cleared, but result uses pre-clear status
        # Original status was 0x83, result should be 0x83 | (0x83 & 0x1F)
        assert result == (0x83 | (0x83 & 0x1F))

    # ---- $2003  OAMADDR  +  $2004  OAMDATA ----

    def test_oamaddr_write(self, ppu: PPU) -> None:
        """Write $2003 sets OAM address."""
        ppu.cpu_write(0x2003, 0x42)
        assert ppu.oam_addr == 0x42

    def test_oamdata_write_and_read(self, ppu: PPU) -> None:
        """Write to $2004 stores at OAMADDR and auto-increments."""
        ppu.cpu_write(0x2003, 0x10)  # set OAM address
        ppu.cpu_write(0x2004, 0xAB)  # write data
        assert ppu.oam[0x10] == 0xAB
        assert ppu.oam_addr == 0x11  # auto-incremented

        # Read back
        ppu.cpu_write(0x2003, 0x10)  # reset address
        val = ppu.cpu_read(0x2004)
        assert val == 0xAB

    # ---- $2005  PPUSCROLL (two-write latch) ----

    def test_ppuscroll_first_write(self, ppu: PPU) -> None:
        """First write to $2005 stores X scroll, latch becomes True."""
        ppu.cpu_write(0x2005, 0x78)
        assert ppu._scroll_x == 0x78
        assert ppu._write_latch is True

    def test_ppuscroll_second_write(self, ppu: PPU) -> None:
        """Second write to $2005 stores Y scroll, latch becomes False."""
        ppu.cpu_write(0x2005, 0x78)  # first  → X scroll
        ppu.cpu_write(0x2005, 0x34)  # second → Y scroll
        assert ppu._scroll_x == 0x78
        assert ppu._scroll_y == 0x34
        assert ppu._write_latch is False

    def test_ppuscroll_third_write_is_first_again(self, ppu: PPU) -> None:
        """Third write to $2005 behaves as a new first write."""
        ppu.cpu_write(0x2005, 0x01)  # X
        ppu.cpu_write(0x2005, 0x02)  # Y
        ppu.cpu_write(0x2005, 0x03)  # new X
        assert ppu._scroll_x == 0x03
        assert ppu._scroll_y == 0x02  # unchanged for now

    # ---- $2006  PPUADDR (two-write latch) ----

    def test_ppuaddr_two_writes(self, ppu: PPU) -> None:
        """Two writes to $2006 build a 14-bit VRAM address (high, low)."""
        ppu.cpu_write(0x2006, 0x23)  # high byte → upper 6 bits stored
        assert ppu.vram_addr == 0x2300
        ppu.cpu_write(0x2006, 0x40)  # low byte
        assert ppu.vram_addr == 0x2340

    def test_ppuaddr_high_byte_masked(self, ppu: PPU) -> None:
        """High byte write to $2006 is masked to 6 bits (bits 6-7 ignored)."""
        ppu.cpu_write(0x2006, 0xFF)  # 0xFF → masked to 0x3F
        ppu.cpu_write(0x2006, 0x00)
        assert ppu.vram_addr == 0x3F00

    # ---- $2007  PPUDATA ----

    def test_ppudata_read_buffer(self, bus: MockPPUBus, ppu: PPU) -> None:
        """Reading $2007 uses the pre-read buffer mechanism."""
        # Set VRAM address to nametable space and put data there
        ppu.cpu_write(0x2006, 0x20)
        ppu.cpu_write(0x2006, 0x00)
        bus.write_nametable(0x2000, [0xDE])

        # First read returns stale read_buffer (0), then pre-reads 0x2000
        val1 = ppu.cpu_read(0x2007)  # returns previous buffer content (0)
        assert val1 == 0

        # Second read returns the pre-read value
        val2 = ppu.cpu_read(0x2007)
        assert val2 == 0xDE

    def test_ppudata_write_and_readback(self, bus: MockPPUBus, ppu: PPU) -> None:
        """Write a value via $2007, then read it back."""
        ppu.cpu_write(0x2006, 0x20)
        ppu.cpu_write(0x2006, 0x00)
        ppu.cpu_write(0x2007, 0x55)

        ppu.cpu_write(0x2006, 0x20)
        ppu.cpu_write(0x2006, 0x00)
        # First read drains buffer, second returns actual value
        ppu.cpu_read(0x2007)
        val = ppu.cpu_read(0x2007)
        assert val == 0x55

    def test_ppudata_palette_mirror_read(self, bus: MockPPUBus, ppu: PPU) -> None:
        """Palette reads ($3F00+) are direct — no buffer lag."""
        ppu.palette[0] = 0x12
        ppu.palette[1] = 0x34

        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)
        # Palette reads return immediately (no one-cycle buffer delay)
        val = ppu.cpu_read(0x2007)
        # For palette reads, value == read_buffer (both set from the same read)
        assert val == 0x12  # or the value read from ppu_bus for 0x3F00

    def test_ppudata_write_palette_mirror(self, ppu: PPU) -> None:
        """Writing $3F10 mirrors to $3F00; writing $3F14 mirrors to $3F04."""
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x10)
        ppu.cpu_write(0x2007, 0x2A)  # should write to palette[0]

        assert ppu.palette[0] == 0x2A  # mirrored from $3F10 → $3F00

    def test_ppudata_write_palette_mirror_3f14(self, ppu: PPU) -> None:
        """Writing $3F14 mirrors to $3F04."""
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x14)
        ppu.cpu_write(0x2007, 0x1B)

        assert ppu.palette[4] == 0x1B

    def test_ppudata_write_palette_mirror_3f18(self, ppu: PPU) -> None:
        """Writing $3F18 mirrors to $3F08."""
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x18)
        ppu.cpu_write(0x2007, 0x3C)

        assert ppu.palette[8] == 0x3C

    def test_ppudata_write_palette_mirror_3f1c(self, ppu: PPU) -> None:
        """Writing $3F1C mirrors to $3F0C."""
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x1C)
        ppu.cpu_write(0x2007, 0x0F)

        assert ppu.palette[12] == 0x0F

    # ---- Address auto-increment ----

    def test_addr_increment_horizontal(self, ppu: PPU) -> None:
        """Horizontal mode (ctrl bit 2 = 0) increments VRAM addr by 1."""
        ppu.cpu_write(0x2000, 0x00)  # bit 2 = 0 → horizontal
        assert ppu._addr_increment() == 1

    def test_addr_increment_vertical(self, ppu: PPU) -> None:
        """Vertical mode (ctrl bit 2 = 1) increments VRAM addr by 32."""
        ppu.cpu_write(0x2000, 0x04)  # bit 2 = 1 → vertical
        assert ppu._addr_increment() == 32

    def test_ppudata_write_auto_increment(self, bus: MockPPUBus, ppu: PPU) -> None:
        """After writing to $2007 the VRAM address auto-increments."""
        ppu.cpu_write(0x2006, 0x20)
        ppu.cpu_write(0x2006, 0x00)
        assert ppu.vram_addr == 0x2000
        ppu.cpu_write(0x2007, 0x42)
        assert ppu.vram_addr == 0x2001  # horizontal increment


# ═══════════════════════════════════════════════════════════════════
#  VBlank / NMI tests
# ═══════════════════════════════════════════════════════════════════

class TestVBlankNMI:
    """Tests for VBlank flag and NMI callback timing."""

    def test_vblank_set_on_scanline_241(self, ppu: PPU) -> None:
        """VBlank flag is set when scanline reaches 241."""
        # Advance to end of scanline 240
        ppu.scanline = 240
        ppu.cycle = 340
        ppu.tick()  # wraps to scanline 241, cycle 0
        assert ppu.scanline == 241
        # tick advances one cycle past the scanline increment
        # At cycle 0 the _set_vblank is called inside the same tick
        assert (ppu.status & 0x80) != 0

    def test_nmi_callback_called(self, ppu: PPU) -> None:
        """NMI callback is invoked when NMI is enabled and VBlank starts."""
        calls: list[int] = []

        def cb() -> None:
            calls.append(1)

        ppu.nmi_callback = cb
        ppu.cpu_write(0x2000, 0x80)  # NMI enabled
        ppu.scanline = 240
        ppu.cycle = 340
        ppu.tick()
        assert len(calls) == 1

    def test_nmi_not_called_when_disabled(self, ppu: PPU) -> None:
        """NMI callback is NOT invoked when NMI is disabled."""
        calls: list[int] = []

        def cb() -> None:
            calls.append(1)

        ppu.nmi_callback = cb
        ppu.cpu_write(0x2000, 0x00)  # NMI disabled (bit 7 = 0)
        ppu.scanline = 240
        ppu.cycle = 340
        ppu.tick()
        assert len(calls) == 0

    def test_nmi_not_called_without_callback(self, ppu: PPU) -> None:
        """No error when NMI fires but no callback is set."""
        ppu.nmi_callback = None
        ppu.cpu_write(0x2000, 0x80)  # NMI enabled
        ppu.scanline = 240
        ppu.cycle = 340
        ppu.tick()
        # Should not raise — just checking it does not crash
        assert (ppu.status & 0x80) != 0

    def test_vblank_cleared_on_prerender(self, ppu: PPU) -> None:
        """VBlank, sprite-0 hit, and sprite overflow are cleared on scanline 261."""
        ppu.status = 0xE0  # VBlank + sprite 0 + sprite overflow
        ppu.scanline = 260
        ppu.cycle = 340
        ppu.tick()  # transitions to scanline 261
        assert ppu.scanline == 261
        assert (ppu.status & 0xE0) == 0  # upper 3 bits cleared


# ═══════════════════════════════════════════════════════════════════
#  OAM DMA tests
# ═══════════════════════════════════════════════════════════════════

class TestOAMDMA:
    """Tests for the OAM DMA interface."""

    def test_oam_write_single_byte(self, ppu: PPU) -> None:
        """oam_write places a byte into OAM at the given index."""
        ppu.oam_write(0, 0x42)
        assert ppu.oam[0] == 0x42

    def test_oam_write_full_range(self, ppu: PPU) -> None:
        """All 256 OAM bytes can be populated via oam_write."""
        for i in range(256):
            ppu.oam_write(i, i & 0xFF)
        for i in range(256):
            assert ppu.oam[i] == (i & 0xFF)

    def test_oam_write_index_wraps(self, ppu: PPU) -> None:
        """oam_write index wraps at 256."""
        ppu.oam_write(256, 0xAB)
        assert ppu.oam[0] == 0xAB


# ═══════════════════════════════════════════════════════════════════
#  Background rendering tests
# ═══════════════════════════════════════════════════════════════════

class TestBackgroundRendering:
    """Tests for background pixel computation."""

    def _setup_basic_bg(
        self,
        bus: MockPPUBus,
        ppu: PPU,
        tile_pattern: list[int] | None = None,
    ) -> None:
        """Configure bus/PPU so that a solid background tile is visible.

        Places tile #0 at nametable (0,0) with a default 8×8 pattern.
        """
        # Enable background rendering
        ppu.cpu_write(0x2001, 0x08)  # only bg visible

        # Nametable 0 (0x2000): tile index 0 at position (0,0)
        bus.write_nametable(0x2000, [0x00] * 32)  # first row — all tile 0

        # Default tile pattern: a filled white square in colour 3
        if tile_pattern is None:
            # 8 bytes low plane + 8 bytes high plane
            # colour index = (high<<1) | low
            # All bytes 0xFF → low=1, high=1 → index 3
            tile_pattern = [0xFF] * 8 + [0xFF] * 8
        bus.load_chr(0x0000, tile_pattern)

    def test_background_pixel_with_known_tile(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Background pixel outputs a non-zero colour from a known tile pattern."""
        # Pattern where bit 0 of each byte is 1 (low plane), bit 1 is 0 → colour 1
        # low plane:  0x01 * 8  (bit 0 set on every pixel)
        # high plane: 0x00 * 8  (bit 1 clear on every pixel)
        # Pattern: low plane = 0x80 (bit 7 = leftmost pixel set)
        #          high plane = 0x00 → colour index = 1
        self._setup_basic_bg(
            bus, ppu,
            tile_pattern=[0x80] * 8 + [0x00] * 8,
        )

        # Set palette values so we can identify the output
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)  # universal bg color
        ppu.cpu_write(0x2007, 0x30)  # palette[0] = index 0x30
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x01)  # bg palette group 0, colour 1
        ppu.cpu_write(0x2007, 0x0C)  # palette[1] = index 0x0C

        color = ppu._get_background_pixel(0, 0)
        assert color != 0
        # colour 0x0C in system palette → check palette.py
        from src.palette import PALETTE
        assert color == PALETTE[0x0C]

    def test_background_disabled_returns_zero(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """When background rendering is off (mask bit 3 = 0), pixel is 0."""
        ppu.cpu_write(0x2001, 0x00)  # all rendering off
        color = ppu._get_background_pixel(0, 0)
        assert color == 0

    def test_scroll_affects_background(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Horizontal scroll shifts the background tile source."""
        # Two different tiles: tile 0 = colour 1 pattern, tile 1 = colour 2 pattern
        # low plane:  first column (pixel 7)=1, rest=0
        # high plane: pixel for tile 1 column 0 has high bit set
        self._setup_basic_bg(bus, ppu,
            # tile 0: colour 1  for the leftmost pixel, colour 0 elsewhere
            tile_pattern=(
                [0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]   # tile 0 low
                + [0x00] * 8                                          # tile 0 high
                + [0x00] * 8                                          # tile 1 low
                + [0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]  # tile 1 high
            ),
        )

        # Place tile 1 at (1, 0) in nametable
        bus.write_nametable(0x2000 + 1, [0x01])

        # Set palette
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)
        ppu.cpu_write(0x2007, 0x20)  # background colour → palette[0]
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x01)
        ppu.cpu_write(0x2007, 0x10)  # palette group 0, colour 1

        # Without scroll, pixel at x=0 comes from tile 0
        c0 = ppu._get_background_pixel(0, 0)
        # With scroll_x=8, pixel at x=0 comes from tile 1
        ppu._scroll_x = 8
        c1 = ppu._get_background_pixel(0, 0)

        # The two values should differ because different tiles → different colours
        assert c0 != c1

    def test_attribute_table_palette_group(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Attribute table selects which of the four background palettes is used."""
        # Each 2×2-tile block shares a palette group via the attribute table
        self._setup_basic_bg(bus, ppu)

        # Set different colours for palette group 0 vs group 1
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)  # universal bg
        ppu.cpu_write(0x2007, 0x0F)

        # Default 0xFF pattern gives colour index 3, so write to colour 3 slots
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x03)  # group 0, colour 3
        ppu.cpu_write(0x2007, 0x10)

        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x07)  # group 1, colour 3
        ppu.cpu_write(0x2007, 0x20)

        # Default attribute is 0 → palette group 0
        c_group0 = ppu._get_background_pixel(0, 0)

        # Set attribute byte for the first 2×2 block at 0x23C0
        # Bits 1-0 correspond to the top-left 2×2 tile group
        bus.write_nametable(0x23C0, [0x01])  # palette group 1
        c_group1 = ppu._get_background_pixel(0, 0)

        assert c_group0 != c_group1


# ═══════════════════════════════════════════════════════════════════
#  Sprite rendering tests
# ═══════════════════════════════════════════════════════════════════

class TestSpriteRendering:
    """Tests for sprite pixel computation."""

    def _setup_sprite_environment(
        self, bus: MockPPUBus, ppu: PPU, sprite_height: int = 8
    ) -> None:
        """Configure mask, ctrl, palette and pattern data for sprite tests."""
        ppu.cpu_write(0x2001, 0x10)  # sprites enabled

        if sprite_height == 8:
            ppu.cpu_write(0x2000, 0x00)  # 8×8 sprites, pattern table $0000
        else:
            ppu.cpu_write(0x2000, 0x20)  # 8×16 sprites

        # Set sprite palette colours
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x11)  # sprite palette group 0, colour 1
        ppu.cpu_write(0x2007, 0x15)

        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x12)  # sprite palette group 0, colour 2
        ppu.cpu_write(0x2007, 0x25)

        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x13)  # sprite palette group 0, colour 3
        ppu.cpu_write(0x2007, 0x35)

    def _set_oam_entry(
        self, ppu: PPU, index: int, y: int, tile: int, attr: int, x: int
    ) -> None:
        """Configure sprite *index* in OAM.

        Uses ``oam_write`` so that the PPU's scanline caches are invalidated
        (important after the scanline-cache optimisation).
        """
        base = index * 4
        ppu.oam_write(base, y)       # Y position (on-screen = y + 1)
        ppu.oam_write(base + 1, tile)  # tile index
        ppu.oam_write(base + 2, attr)  # attributes
        ppu.oam_write(base + 3, x)    # X position

    def test_sprite_disabled_returns_zero(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """When sprite rendering is off, no sprite pixel is produced."""
        ppu.cpu_write(0x2001, 0x00)  # sprites disabled
        color, priority, sz = ppu._get_sprite_pixel(0, 0)
        assert color == 0
        assert priority == 0
        assert sz is False

    def test_sprite_pixel_visible(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """A sprite with visible pixels produces non-zero colour."""
        self._setup_sprite_environment(bus, ppu)

        # Tile 0 pattern: all pixels colour 3
        bus.load_chr(0x0000, [0xFF] * 8 + [0xFF] * 8)

        # Sprite 0 at (0, 0) with tile 0, no flip, palette group 0
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0, x=0)
        # y=255 means on-screen y = 256 → but y wraps, so y=0 on screen
        # Actually: on-screen y = OAM y + 1, so for sprite to appear at y=0,
        # OAM y should be 0xFF (255) because (255+1) & 0xFF = 0

        color, priority, sz = ppu._get_sprite_pixel(0, 0)
        assert color != 0

    def test_sprite_priority(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Sprite priority bit controls foreground/background ordering."""
        self._setup_sprite_environment(bus, ppu)

        # Tile 0 pattern: all pixels colour 3
        bus.load_chr(0x0000, [0xFF] * 8 + [0xFF] * 8)

        # Sprite with priority bit set (behind background)
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x20, x=0)
        # attr 0x20 → priority = 1 (behind background)

        _, priority, _ = ppu._get_sprite_pixel(0, 0)
        assert priority == 1

        # Sprite with no priority bit (in front of background)
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)
        _, priority, _ = ppu._get_sprite_pixel(0, 0)
        assert priority == 0

    def test_sprite_horizontal_flip(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Horizontal flip reverses pixel column order."""
        self._setup_sprite_environment(bus, ppu)

        # Pattern where only the leftmost pixel of tile has colour 3
        # low plane byte 0: 0x80 (bit 7 = leftmost pixel = 1)
        # high plane byte 0: 0x80 (bit 7 = 1) → colour index 3
        bus.load_chr(0x0000, (
            [0x80] + [0x00] * 7   # low plane — only leftmost pixel set
            + [0x80] + [0x00] * 7 # high plane — only leftmost pixel set
        ))

        # No flip: pixel visible at x=0 (left edge)
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)
        color_noflip, _, _ = ppu._get_sprite_pixel(0, 0)
        assert color_noflip != 0

        # With horizontal flip: leftmost pattern pixel now at x=7
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x40, x=0)
        color_flipped_at_0, _, _ = ppu._get_sprite_pixel(0, 0)
        assert color_flipped_at_0 == 0  # x=0 is now the rightmost pixel (transparent)

        # The visible pixel should be at x=7
        color_flipped_at_7, _, _ = ppu._get_sprite_pixel(7, 0)
        assert color_flipped_at_7 != 0

    def test_sprite_vertical_flip(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Vertical flip reverses pixel row order."""
        self._setup_sprite_environment(bus, ppu)

        # Pattern where only top row has colour 3
        bus.load_chr(0x0000, (
            [0xFF] + [0x00] * 7   # low plane — only top row set
            + [0xFF] + [0x00] * 7 # high plane — only top row set
        ))

        # No flip: pixel visible at y=0 (top of sprite)
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)
        color_noflip, _, _ = ppu._get_sprite_pixel(0, 0)
        assert color_noflip != 0

        # With vertical flip: top row now at y=7
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x80, x=0)
        color_flipped_at_0, _, _ = ppu._get_sprite_pixel(0, 0)
        assert color_flipped_at_0 == 0  # y=0 is now the bottom row (transparent)

        # The visible pixel should be at y=7
        color_flipped_at_7, _, _ = ppu._get_sprite_pixel(0, 7)
        assert color_flipped_at_7 != 0

    def test_sprite_zero_collision(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Sprite-0 collision flag is set when sprite 0 and bg both non-transparent."""
        # Enable both bg and sprites
        ppu.cpu_write(0x2001, 0x18)
        ppu.cpu_write(0x2000, 0x00)

        # Set up background — colour 3 tile
        bus.load_chr(0x0000, [0xFF] * 8 + [0xFF] * 8)
        bus.write_nametable(0x2000, [0x00] * 32)

        # Set up sprite 0 — colour 3 tile, positioned at same location
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)

        # Set palette values
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)
        ppu.cpu_write(0x2007, 0x0F)  # bg colour
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x01)
        ppu.cpu_write(0x2007, 0x10)  # bg palette group 0, colour 1
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x11)
        ppu.cpu_write(0x2007, 0x20)  # sprite palette group 0, colour 1

        # Render one pixel — should trigger sprite-0 collision
        ppu._render_pixel(0, 0)
        assert (ppu.status & 0x40) != 0  # sprite-0 hit flag set

    def test_sprite_zero_no_collision_at_x255(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Sprite-0 collision is not triggered at x=255."""
        ppu.cpu_write(0x2001, 0x18)
        ppu.cpu_write(0x2000, 0x00)

        bus.load_chr(0x0000, [0xFF] * 8 + [0xFF] * 8)
        bus.write_nametable(0x2000, [0x00] * 32)

        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)

        # Set palette
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)
        ppu.cpu_write(0x2007, 0x0F)
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x01)
        ppu.cpu_write(0x2007, 0x10)
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x11)
        ppu.cpu_write(0x2007, 0x20)

        # Background at x=255 depends on scroll — set scroll so that
        # tile 0 covers this area (no scroll offset)
        ppu._render_pixel(255, 0)
        assert (ppu.status & 0x40) == 0  # sprite-0 hit NOT set at x=255

    def test_sprite_8x16_mode(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """In 8×16 mode sprites are 16 pixels tall, using two pattern tiles."""
        self._setup_sprite_environment(bus, ppu, sprite_height=16)

        # Pattern table 0: tile 0 (top half) — colour 3 on first row
        bus.load_chr(0x0000, (
            [0xFF] + [0x00] * 7 + [0xFF] + [0x00] * 7  # tile 0 top
        ))
        # tile 1 (bottom half) — colour 3 on first row of tile 1
        bus.load_chr(0x0010, (
            [0xFF] + [0x00] * 7 + [0xFF] + [0x00] * 7  # tile 1
        ))

        # Sprite uses tile 0 (top), bottom half is tile 1
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)

        # Top half (row 0 of sprite → row 0 of tile 0)
        c_top, _, _ = ppu._get_sprite_pixel(0, 0)
        assert c_top != 0

        # Bottom half (row 8 of sprite → row 0 of tile 1)
        c_bottom, _, _ = ppu._get_sprite_pixel(0, 8)
        assert c_bottom != 0

    def test_sprite_transparent_pixels(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """Colour-index-0 sprite pixels are transparent and do not render."""
        self._setup_sprite_environment(bus, ppu)

        # Tile pattern: all zeros → colour index 0 everywhere (fully transparent)
        bus.load_chr(0x0000, [0x00] * 16)

        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)

        color, _, _ = ppu._get_sprite_pixel(0, 0)
        assert color == 0

    def test_sprite_oob_y(self, bus: MockPPUBus, ppu: PPU) -> None:
        """Sprite outside the current scanline returns transparent."""
        self._setup_sprite_environment(bus, ppu)
        bus.load_chr(0x0000, [0xFF] * 16)
        # Sprite at y=200 (on-screen y=201), querying y=0
        self._set_oam_entry(ppu, 0, y=200, tile=0, attr=0x00, x=0)
        color, _, _ = ppu._get_sprite_pixel(0, 0)
        assert color == 0

    def test_sprite_highest_priority_wins(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """When two sprites overlap, the lower OAM index (higher priority) is visible."""
        self._setup_sprite_environment(bus, ppu)

        # Tile 0: all colour 3; Tile 1: all colour 2
        bus.load_chr(0x0000, [0xFF] * 16)   # tile 0
        bus.load_chr(0x0010, [0xFF] * 16)   # tile 1

        # Sprite 0 (high priority) at (0,0) with tile 0
        self._set_oam_entry(ppu, 0, y=255, tile=0, attr=0x00, x=0)
        # Sprite 1 (lower priority) at same position with tile 1
        self._set_oam_entry(ppu, 1, y=255, tile=1, attr=0x00, x=0)

        # Render pixel at (0,0) — sprite 0 should win
        ppu._render_pixel(0, 0)

        # Both should have colour 3 since both tiles are [0xFF]×16
        # But the important thing is that sprite 0 is checked first
        color, _, is_s0 = ppu._get_sprite_pixel(0, 0)
        assert color != 0
        assert is_s0 is True  # comes from sprite 0


# ═══════════════════════════════════════════════════════════════════
#  Frame buffer / full-frame tests
# ═══════════════════════════════════════════════════════════════════

class TestFrameBuffer:
    """Tests for the framebuffer and frame completion."""

    def test_framebuffer_initialized(self, ppu: PPU) -> None:
        """Framebuffer is a list of 256×240 zeroes on creation."""
        assert len(ppu.framebuffer) == 256 * 240
        assert all(c == 0 for c in ppu.framebuffer)

    def test_frame_complete_flag(self, ppu: PPU) -> None:
        """After running a full frame, frame_complete is True."""
        ppu.cpu_write(0x2001, 0x00)  # disable rendering for speed
        # Run through a full NTSC frame (262 scanlines × 341 ticks each)
        # We stop when frame_complete becomes True
        max_ticks = 262 * 341
        for _ in range(max_ticks):
            ppu.tick()
            if ppu.frame_complete:
                break
        assert ppu.frame_complete is True

    def test_frame_complete_set_on_scanline_261(self, ppu: PPU) -> None:
        """frame_complete is set precisely when scanline 261 is reached."""
        ppu.cpu_write(0x2001, 0x00)
        # Advance to just before scanline 261
        ppu.scanline = 260
        ppu.cycle = 340
        assert ppu.frame_complete is False
        ppu.tick()  # transitions to scanline 261
        assert ppu.scanline == 261
        assert ppu.frame_complete is True

    def test_reset_clears_all_state(self, ppu: PPU) -> None:
        """reset() returns PPU to initial state."""
        ppu.ctrl = 0xFF
        ppu.mask = 0xFF
        ppu.status = 0xFF
        ppu._write_latch = True
        ppu.scanline = 100
        ppu.cycle = 200
        ppu.frame_complete = True
        ppu.oam[0] = 0x42
        ppu.palette[0] = 0x3F

        ppu.reset()

        assert ppu.ctrl == 0
        assert ppu.mask == 0
        assert ppu.status == 0
        assert ppu._write_latch is False
        assert ppu.scanline == 0
        assert ppu.cycle == 0
        assert ppu.frame_complete is False
        assert ppu.oam[0] == 0
        assert ppu.palette[0] == 0

    def test_framebuffer_populated_after_frame(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """After rendering a frame, the framebuffer contains pixel values."""
        ppu.cpu_write(0x2001, 0x08)  # bg enabled
        ppu.cpu_write(0x2000, 0x00)

        # Set up nametable with tile 0 everywhere
        bus.write_nametable(0x2000, [0x00] * 960)
        bus.load_chr(0x0000, [0xFF] * 16)  # solid colour 3 tile

        # Set palette
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)
        ppu.cpu_write(0x2007, 0x15)
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x01)
        ppu.cpu_write(0x2007, 0x0F)

        # Run one frame
        for _ in range(262 * 341):
            ppu.tick()
            if ppu.frame_complete:
                break

        # Check that some pixels are non-zero
        nonzero = sum(1 for c in ppu.framebuffer if c != 0)
        assert nonzero > 0  # at least some pixels were rendered

    def test_render_pixel_compositing(
        self, bus: MockPPUBus, ppu: PPU
    ) -> None:
        """_render_pixel writes to the correct framebuffer index."""
        ppu._render_pixel(10, 20)
        # With rendering off, the pixel should be 0
        assert ppu.framebuffer[20 * 256 + 10] == 0

        # Now with bg enabled
        ppu.cpu_write(0x2001, 0x08)
        bus.write_nametable(0x2000, [0x00] * 960)
        bus.load_chr(0x0000, [0xFF] * 16)
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x00)
        ppu.cpu_write(0x2007, 0x15)
        ppu.cpu_write(0x2006, 0x3F)
        ppu.cpu_write(0x2006, 0x01)
        ppu.cpu_write(0x2007, 0x0F)

        ppu._render_pixel(10, 20)
        assert ppu.framebuffer[20 * 256 + 10] != 0
