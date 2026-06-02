"""FC/NES Cartridge module — iNES ROM parsing and Mapper 0 (NROM) support."""

from __future__ import annotations

_INES_MAGIC = b"NES\x1a"
_HEADER_SIZE = 16
_TRAINER_SIZE = 512
_PRG_BANK_SIZE = 16384  # 16 KB per PRG-ROM bank
_CHR_BANK_SIZE = 8192  # 8 KB per CHR-ROM bank


class Cartridge:
    """FC/NES cartridge simulator, supports Mapper 0 (NROM)."""

    def __init__(self, rom_data: bytes) -> None:
        """Parse ROM from bytes data.

        Accepting bytes (rather than a file path) makes unit testing easy —
        callers can construct ROM data directly. Production code reads the
        file into bytes first, then passes them here.

        Args:
            rom_data: The complete ROM file contents as bytes.

        Raises:
            ValueError: If the ROM magic number is incorrect.

        """
        if rom_data[:4] != _INES_MAGIC:
            raise ValueError(
                f"Invalid iNES magic number: {rom_data[:4]!r} (expected {_INES_MAGIC!r})"
            )

        self.prg_banks: int = rom_data[4]
        self.chr_banks: int = rom_data[5]
        flag6: int = rom_data[6]
        flag7: int = rom_data[7]

        self.mirror_mode: int = flag6 & 0x01  # 0 = horizontal, 1 = vertical
        has_trainer: bool = bool((flag6 >> 2) & 0x01)
        self.mapper_id: int = (flag7 & 0xF0) | (flag6 >> 4)

        prg_size: int = self.prg_banks * _PRG_BANK_SIZE
        chr_size: int = self.chr_banks * _CHR_BANK_SIZE

        data_offset: int = _HEADER_SIZE
        if has_trainer:
            data_offset += _TRAINER_SIZE

        self.prg_rom: bytearray = bytearray(rom_data[data_offset : data_offset + prg_size])
        data_offset += prg_size
        self.chr_rom: bytearray = bytearray(rom_data[data_offset : data_offset + chr_size])

    # ---- Mapper 0 CPU read / write ----

    def cpu_read(self, address: int) -> int:
        """CPU-side PRG-ROM read ($8000-$FFFF).

        Mapper 0 mapping rules:
        - 1 x 16 KB bank → mirrored to $8000-$BFFF and $C000-$FFFF
        - 2 x 16 KB banks → $8000-$BFFF = bank 0, $C000-$FFFF = bank 1

        Returns 0 when *address* < 0x8000.
        """
        if address < 0x8000:
            return 0
        index: int = (address - 0x8000) % len(self.prg_rom)
        return self.prg_rom[index]

    def cpu_write(self, address: int, value: int) -> None:
        """CPU-side write. Mapper 0 uses ROM — writes are ignored."""

    # ---- Mapper 0 PPU read / write ----

    def ppu_read(self, address: int) -> int:
        """PPU-side CHR-ROM read ($0000-$1FFF).

        Returns 0 when *address* >= 0x2000 or CHR-ROM is empty.
        """
        if address >= 0x2000 or len(self.chr_rom) == 0:
            return 0
        return self.chr_rom[address % len(self.chr_rom)]

    def ppu_write(self, address: int, value: int) -> None:
        """PPU-side write. Mapper 0 uses CHR-ROM (read-only) — writes are ignored."""
