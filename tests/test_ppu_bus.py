"""Unit tests for src/ppu_bus.py — PPU address-space bus."""

from __future__ import annotations

from src.ppu_bus import HORIZONTAL, VERTICAL, PPUBus

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockCartridge:
    """Mock Cartridge that records PPU-side reads/writes."""

    def __init__(self) -> None:
        """Create a MockCartridge with empty log lists."""
        self.ppu_read_log: list[int] = []
        self.ppu_write_log: list[tuple[int, int]] = []

    def ppu_read(self, address: int) -> int:
        """Log the address and return a value derived from it."""
        self.ppu_read_log.append(address)
        return (address & 0xFF) ^ 0x55

    def ppu_write(self, address: int, value: int) -> None:
        """Log the address and value."""
        self.ppu_write_log.append((address, value))


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestCHRROM:
    """CHR-ROM ($0000-$1FFF) routing tests."""

    def test_chr_rom_read(self) -> None:
        """$0000 routes to Cartridge.ppu_read."""
        cart = MockCartridge()
        ppu_bus = PPUBus(cartridge=cart)
        result = ppu_bus.read(0x0000)
        assert result == 0x55  # (0 ^ 0x55)
        assert cart.ppu_read_log == [0x0000]

    def test_chr_rom_read_mid_range(self) -> None:
        """Somewhere inside CHR-ROM space routes correctly."""
        cart = MockCartridge()
        ppu_bus = PPUBus(cartridge=cart)
        assert ppu_bus.read(0x10AB) == (0x10AB & 0xFF) ^ 0x55
        assert cart.ppu_read_log == [0x10AB]

    def test_chr_rom_write(self) -> None:
        """Write to CHR-ROM space routes to Cartridge.ppu_write (CHR-RAM)."""
        cart = MockCartridge()
        ppu_bus = PPUBus(cartridge=cart)
        ppu_bus.write(0x0000, 0x77)
        assert cart.ppu_write_log == [(0x0000, 0x77)]


class TestNametable:
    """Nametable ($2000-$3EFF) read/write tests."""

    def test_nametable_read_write(self) -> None:
        """Basic Nametable read/write at $2000."""
        ppu_bus = PPUBus()
        ppu_bus.write(0x2000, 0xAB)
        assert ppu_bus.read(0x2000) == 0xAB

    def test_nametable_write_read_many(self) -> None:
        """Write multiple bytes to the Nametable and read them back."""
        ppu_bus = PPUBus()
        for i in range(256):
            ppu_bus.write(0x2000 + i, i & 0xFF)
        for i in range(256):
            assert ppu_bus.read(0x2000 + i) == (i & 0xFF)


class TestHorizontalMirror:
    """Horizontal mirroring tests."""

    def test_horizontal_mirror(self) -> None:
        """Horizontal: $2000 mirrors $2400 (same physical table)."""
        ppu_bus = PPUBus(mirror_mode=HORIZONTAL)
        ppu_bus.write(0x2000, 0x12)
        assert ppu_bus.read(0x2400) == 0x12

    def test_horizontal_mirror_table23(self) -> None:
        """Horizontal: $2800 mirrors $2C00."""
        ppu_bus = PPUBus(mirror_mode=HORIZONTAL)
        ppu_bus.write(0x2800, 0x34)
        assert ppu_bus.read(0x2C00) == 0x34

    def test_horizontal_mirror_no_cross_table(self) -> None:
        """Horizontal: $2000 is NOT mirrored to $2800 (different physical)."""
        ppu_bus = PPUBus(mirror_mode=HORIZONTAL)
        ppu_bus.write(0x2000, 0xAA)
        ppu_bus.write(0x2800, 0xBB)
        assert ppu_bus.read(0x2000) == 0xAA
        assert ppu_bus.read(0x2800) == 0xBB

    def test_horizontal_mirror_offset_preserved(self) -> None:
        """Mirroring preserves the intra-table offset."""
        ppu_bus = PPUBus(mirror_mode=HORIZONTAL)
        ppu_bus.write(0x2000, 0x01)
        ppu_bus.write(0x20FF, 0x02)
        assert ppu_bus.read(0x2400) == 0x01  # offset 0 in table 1 mirrors table 0
        assert ppu_bus.read(0x24FF) == 0x02  # offset 255 in table 1 mirrors table 0


class TestVerticalMirror:
    """Vertical mirroring tests."""

    def test_vertical_mirror(self) -> None:
        """Vertical: $2000 mirrors $2800."""
        ppu_bus = PPUBus(mirror_mode=VERTICAL)
        ppu_bus.write(0x2000, 0xAB)
        assert ppu_bus.read(0x2800) == 0xAB

    def test_vertical_mirror_table13(self) -> None:
        """Vertical: $2400 mirrors $2C00."""
        ppu_bus = PPUBus(mirror_mode=VERTICAL)
        ppu_bus.write(0x2400, 0xCD)
        assert ppu_bus.read(0x2C00) == 0xCD

    def test_vertical_mirror_no_cross_table(self) -> None:
        """Vertical: $2000 is NOT mirrored to $2400."""
        ppu_bus = PPUBus(mirror_mode=VERTICAL)
        ppu_bus.write(0x2000, 0x11)
        ppu_bus.write(0x2400, 0x22)
        assert ppu_bus.read(0x2000) == 0x11
        assert ppu_bus.read(0x2400) == 0x22

    def test_vertical_mirror_offset_preserved(self) -> None:
        """Vertical mirroring preserves the intra-table offset."""
        ppu_bus = PPUBus(mirror_mode=VERTICAL)
        ppu_bus.write(0x2000, 0x5A)
        ppu_bus.write(0x2040, 0xA5)
        assert ppu_bus.read(0x2800) == 0x5A  # offset 0
        assert ppu_bus.read(0x2840) == 0xA5  # offset 64


class TestNametableBoundary:
    """Nametable mirror boundary tests."""

    def test_nametable_mirror_boundary(self) -> None:
        """Address at the high end of Nametable area ($3EFF) is handled correctly.

        $3EFF is in the mirrored portion ($3000-$3EFF mirrors $2000-$2EFF).
        It maps to logical table 3, offset 0x2FF.
        In HORIZONTAL mode, table 3 → physical table 1 (same as table 2).
        So $3EFF is readable at $2EFF (which also maps to physical table 1,
        offset 0x2FF).
        """
        ppu_bus = PPUBus(mirror_mode=HORIZONTAL)
        ppu_bus.write(0x3EFF, 0xEE)
        # Reading from the same address works (mirrors back through same logic).
        assert ppu_bus.read(0x3EFF) == 0xEE
        # $2EFF maps to same physical location (table 2→physical 1).
        assert ppu_bus.read(0x2EFF) == 0xEE

    def test_mirror_addresses_inside_nametable_range(self) -> None:
        """All addresses $2000-$2FFF map to valid nametable offsets 0-2047."""
        ppu_bus = PPUBus(mirror_mode=HORIZONTAL)
        # Write to every offset within the first table
        for addr in range(0x2000, 0x2400):
            ppu_bus.write(addr, addr & 0xFF)
        # Read back and verify (all should be readable from the same physical table)
        for addr in range(0x2000, 0x2400):
            expected = addr & 0xFF
            assert ppu_bus.read(addr) == expected


class TestPalette:
    """Palette area ($3F00-$3FFF) tests."""

    def test_palette_area_returns_zero(self) -> None:
        """$3F00+ returns 0 from PPUBus (PPU manages palette internally)."""
        ppu_bus = PPUBus()
        assert ppu_bus.read(0x3F00) == 0
        assert ppu_bus.read(0x3F10) == 0
        assert ppu_bus.read(0x3FFF) == 0

    def test_palette_area_write_ignored(self) -> None:
        """Writes to palette area are ignored by PPUBus (not routed)."""
        ppu_bus = PPUBus()
        # These should not crash
        ppu_bus.write(0x3F00, 0x30)
        ppu_bus.write(0x3F1F, 0x20)
        # Nametable should be unaffected
        ppu_bus.write(0x2000, 0xAB)
        assert ppu_bus.read(0x2000) == 0xAB


class TestEdgeCases:
    """Edge case tests for PPUBus."""

    def test_address_wraps_14bit(self) -> None:
        """PPU addresses are masked to 14 bits ($3FFF)."""
        cart = MockCartridge()
        ppu_bus = PPUBus(cartridge=cart)
        # $4000 wraps to $0000
        _result = ppu_bus.read(0x4000)
        assert cart.ppu_read_log == [0x0000]

    def test_value_clamped_to_8bit(self) -> None:
        """Values written are clamped to 8 bits."""
        ppu_bus = PPUBus()
        ppu_bus.write(0x2000, 0x1FF)  # only 0xFF should be written
        assert ppu_bus.read(0x2000) == 0xFF

    def test_no_cartridge_no_crash(self) -> None:
        """PPUBus works without a cartridge (returns 0 for CHR-ROM)."""
        ppu_bus = PPUBus(cartridge=None)
        assert ppu_bus.read(0x0000) == 0
        assert ppu_bus.read(0x1000) == 0
        # Nametable should still work
        ppu_bus.write(0x2000, 0x42)
        assert ppu_bus.read(0x2000) == 0x42

    def test_default_mirror_mode(self) -> None:
        """Default mirror_mode is HORIZONTAL."""
        ppu_bus = PPUBus()
        # HORIZONTAL: $2000 = $2400
        ppu_bus.write(0x2000, 0x77)
        assert ppu_bus.read(0x2400) == 0x77

    def test_mirror_mode_constants(self) -> None:
        """HORIZONTAL=0, VERTICAL=1 match iNES conventions."""
        assert HORIZONTAL == 0
        assert VERTICAL == 1
