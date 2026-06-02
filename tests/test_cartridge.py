"""Unit tests for src/cartridge.py."""

from __future__ import annotations

import os
import struct

import pytest

from src.cartridge import Cartridge

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INES_MAGIC = b"NES\x1a"
_PRG_BANK_SIZE = 16384
_CHR_BANK_SIZE = 8192
_HEADER_SIZE = 16


def _build_rom(
    *,
    prg_banks: int = 1,
    chr_banks: int = 1,
    mapper_id: int = 0,
    mirror_mode: int = 0,
    has_trainer: bool = False,
    prg_data: bytes | None = None,
    chr_data: bytes | None = None,
) -> bytes:
    """Build a minimal valid iNES ROM as bytes."""
    flag6: int = (mirror_mode & 0x01) | ((mapper_id & 0x0F) << 4)
    if has_trainer:
        flag6 |= 0x04  # bit 2
    flag7: int = (mapper_id & 0xF0)

    header: bytes = bytearray(_HEADER_SIZE)
    header[0:4] = _INES_MAGIC
    header[4] = prg_banks
    header[5] = chr_banks
    header[6] = flag6
    header[7] = flag7

    rom: bytes = bytes(header)
    if has_trainer:
        rom += b"\x00" * 512

    if prg_data is None:
        prg_data = bytes(i & 0xFF for i in range(prg_banks * _PRG_BANK_SIZE))
    rom += prg_data

    if chr_data is None:
        chr_data = bytes(i & 0xFF for i in range(chr_banks * _CHR_BANK_SIZE))
    rom += chr_data

    return rom


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCartridgeHeaderParsing:
    """Tests covering iNES header validation and field extraction."""

    def test_valid_ines_header(self) -> None:
        """Construct a valid iNES header and verify all parsed fields."""
        rom = _build_rom(prg_banks=2, chr_banks=1, mapper_id=0, mirror_mode=1)
        cart = Cartridge(rom)

        assert cart.prg_banks == 2
        assert cart.chr_banks == 1
        assert cart.mapper_id == 0
        assert cart.mirror_mode == 1
        assert len(cart.prg_rom) == 2 * _PRG_BANK_SIZE
        assert len(cart.chr_rom) == 1 * _CHR_BANK_SIZE

    def test_invalid_magic_number(self) -> None:
        """An incorrect magic number should raise ValueError."""
        bad_header: bytes = b"NES\x1B" + b"\x00" * 12
        with pytest.raises(ValueError, match="Invalid iNES magic number"):
            Cartridge(bad_header)

    def test_mapper_id_parsing(self) -> None:
        """Verify Mapper ID is composed correctly from flag6 and flag7."""
        # Mapper 1 (MMC1): flag6=0x10, flag7=0x00  → mapper_id = 0x01
        rom = _build_rom(mapper_id=1)
        cart = Cartridge(rom)
        assert cart.mapper_id == 1

        # Mapper 4 (MMC3): flag6=0x40, flag7=0x00  → mapper_id = 0x04
        rom = _build_rom(mapper_id=4)
        cart = Cartridge(rom)
        assert cart.mapper_id == 4

        # Mapper 71: flag6=0x70, flag7=0x40  → mapper_id = 0x47 = 71
        rom = _build_rom(mapper_id=71)
        cart = Cartridge(rom)
        assert cart.mapper_id == 71

    def test_mirror_mode(self) -> None:
        """Horizontal (0) and vertical (1) mirror modes are parsed correctly."""
        cart_h = Cartridge(_build_rom(mirror_mode=0))
        assert cart_h.mirror_mode == 0

        cart_v = Cartridge(_build_rom(mirror_mode=1))
        assert cart_v.mirror_mode == 1

    def test_prg_rom_data_content(self) -> None:
        """Verify that PRG-ROM bytes are correctly extracted from the ROM file."""
        test_data: bytes = b"\xDE\xAD\xBE\xEF" + bytes(_PRG_BANK_SIZE - 4)
        rom = _build_rom(prg_banks=1, prg_data=test_data)
        cart = Cartridge(rom)

        assert cart.prg_rom[0] == 0xDE
        assert cart.prg_rom[1] == 0xAD
        assert cart.prg_rom[2] == 0xBE
        assert cart.prg_rom[3] == 0xEF


class TestCartridgeMapper0:
    """Tests covering Mapper 0 CPU and PPU read/write logic."""

    def test_cpu_read_single_bank(self) -> None:
        """Single PRG bank (16 KB) is mirrored across $8000-$FFFF."""
        prg: bytes = bytes([i & 0xFF for i in range(_PRG_BANK_SIZE)])
        rom = _build_rom(prg_banks=1, prg_data=prg)
        cart = Cartridge(rom)

        # $8000 maps to PRG-ROM offset 0
        assert cart.cpu_read(0x8000) == prg[0]
        # $C000 maps to PRG-ROM offset 0 (mirror)
        assert cart.cpu_read(0xC000) == prg[0]
        # $8001 maps to PRG-ROM offset 1
        assert cart.cpu_read(0x8001) == prg[1]
        # $C001 maps to PRG-ROM offset 1 (mirror)
        assert cart.cpu_read(0xC001) == prg[1]

    def test_cpu_read_two_banks(self) -> None:
        """Two PRG banks (32 KB): $8000-$BFFF = bank 0, $C000-$FFFF = bank 1."""
        bank0: bytes = bytes([0xAA] * _PRG_BANK_SIZE)
        bank1: bytes = bytes([0xBB] * _PRG_BANK_SIZE)
        rom = _build_rom(prg_banks=2, prg_data=bank0 + bank1)
        cart = Cartridge(rom)

        assert cart.cpu_read(0x8000) == 0xAA  # bank 0
        assert cart.cpu_read(0xBFFF) == 0xAA  # bank 0
        assert cart.cpu_read(0xC000) == 0xBB  # bank 1
        assert cart.cpu_read(0xFFFF) == 0xBB  # bank 1

    def test_cpu_read_below_8000_returns_zero(self) -> None:
        """Addresses below $8000 are not PRG-ROM space — return 0."""
        rom = _build_rom()
        cart = Cartridge(rom)

        assert cart.cpu_read(0x0000) == 0
        assert cart.cpu_read(0x7FFF) == 0

    def test_cpu_write_is_noop(self) -> None:
        """CPU write to Mapper 0 does nothing (ROM is read-only)."""
        rom = _build_rom()
        cart = Cartridge(rom)

        original: int = cart.cpu_read(0x8000)
        cart.cpu_write(0x8000, 0x42)
        # Value should be unchanged — writes are ignored
        assert cart.cpu_read(0x8000) == original

    def test_ppu_read_chr_rom(self) -> None:
        """CHR-ROM is correctly read via ppu_read."""
        chr_data: bytes = bytes([i & 0xFF for i in range(_CHR_BANK_SIZE)])
        rom = _build_rom(chr_banks=1, chr_data=chr_data)
        cart = Cartridge(rom)

        assert cart.ppu_read(0x0000) == chr_data[0]
        assert cart.ppu_read(0x1FFF) == chr_data[-1]
        assert cart.ppu_read(0x0001) == chr_data[1]

    def test_ppu_read_beyond_1fff_returns_zero(self) -> None:
        """Addresses >= $2000 are not CHR-ROM space."""
        rom = _build_rom(chr_banks=1)
        cart = Cartridge(rom)

        assert cart.ppu_read(0x2000) == 0
        assert cart.ppu_read(0x3FFF) == 0

    def test_ppu_read_no_chr_rom_returns_zero(self) -> None:
        """When CHR-ROM is empty (CHR-RAM), ppu_read returns 0."""
        rom = _build_rom(chr_banks=0, chr_data=b"")
        cart = Cartridge(rom)

        assert len(cart.chr_rom) == 0
        assert cart.ppu_read(0x0000) == 0
        assert cart.ppu_read(0x1000) == 0

    def test_ppu_write_is_noop(self) -> None:
        """PPU write to Mapper 0 does nothing (CHR-ROM is read-only)."""
        chr_data: bytes = bytes([0x42] * _CHR_BANK_SIZE)
        rom = _build_rom(chr_banks=1, chr_data=chr_data)
        cart = Cartridge(rom)

        original: int = cart.ppu_read(0x0000)
        cart.ppu_write(0x0000, 0xFF)
        assert cart.ppu_read(0x0000) == original


class TestCartridgeTrainer:
    """Tests covering Trainer data handling."""

    def test_trainer_skip(self) -> None:
        """When the Trainer flag is set, the 512-byte Trainer is skipped."""
        trainer_bytes: bytes = struct.pack(">I", 0xDEADBEEF) + b"\x00" * 508
        rom = _build_rom(
            prg_banks=1,
            chr_banks=1,
            has_trainer=True,
            prg_data=bytes([0x11] * _PRG_BANK_SIZE),
            chr_data=bytes([0x22] * _CHR_BANK_SIZE),
        )
        # Manually insert distinct trainer after header
        header: bytes = rom[:16]
        trainer: bytes = trainer_bytes
        prg: bytes = rom[16 + 512 : 16 + 512 + _PRG_BANK_SIZE]
        chr_: bytes = rom[16 + 512 + _PRG_BANK_SIZE :]
        modified_rom: bytes = header + trainer + prg + chr_

        cart = Cartridge(modified_rom)

        assert cart.prg_rom[0] == 0x11  # Not trainer data
        assert cart.chr_rom[0] == 0x22


class TestCartridgeRealROM:
    """Integration test with a real Super Mario Bros. ROM file."""

    def test_load_real_rom(self) -> None:
        """Load Super Mario Bros. ROM and verify known header values."""
        rom_path: str = os.path.join(
            os.path.dirname(__file__),
            "..",
            "Super Mario Bros. (E) (PRG0) [!].nes",
        )
        if not os.path.isfile(rom_path):
            pytest.skip("Super Mario Bros. ROM file not found — skipping integration test.")

        with open(rom_path, "rb") as fh:
            rom_data: bytes = fh.read()
        cart = Cartridge(rom_data)

        assert cart.mapper_id == 0
        assert cart.prg_banks == 2
        assert cart.chr_banks == 1
        assert len(cart.prg_rom) == 2 * _PRG_BANK_SIZE  # 32 KB
        assert len(cart.chr_rom) == 1 * _CHR_BANK_SIZE  # 8 KB
