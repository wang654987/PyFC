"""Unit tests for src/bus.py — CPU address-space bus."""

from __future__ import annotations

from src.bus import Bus

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockPPU:
    """Mock PPU that logs every call instead of doing real work."""

    def __init__(self) -> None:
        """Create a MockPPU with empty log lists."""
        self.read_log: list[int] = []
        self.write_log: list[tuple[int, int]] = []
        self.oam_log: list[tuple[int, int]] = []

    def cpu_read(self, addr: int) -> int:
        """Log the address and return a dummy value."""
        self.read_log.append(addr)
        return 0x42

    def cpu_write(self, addr: int, value: int) -> None:
        """Log the address and value."""
        self.write_log.append((addr, value))

    def oam_write(self, addr: int, value: int) -> None:
        """Log the OAM address and value."""
        self.oam_log.append((addr, value))


class MockCartridge:
    """Mock Cartridge that records CPU-side reads/writes."""

    def __init__(self) -> None:
        """Create a MockCartridge with empty log lists."""
        self.read_log: list[int] = []
        self.write_log: list[tuple[int, int]] = []

    def cpu_read(self, address: int) -> int:
        """Log the address and return a value derived from it."""
        self.read_log.append(address)
        return (address & 0xFF) ^ 0xAA

    def cpu_write(self, address: int, value: int) -> None:
        """Log the address and value."""
        self.write_log.append((address, value))


class MockController:
    """Mock Controller that records reads/writes."""

    def __init__(self) -> None:
        """Create a MockController with empty log lists."""
        self.read_log: list[None] = []
        self.write_log: list[int] = []

    def read(self) -> int:
        """Log the call and return a dummy value."""
        self.read_log.append(None)
        return 0x55

    def write(self, value: int) -> None:
        """Log the written value."""
        self.write_log.append(value)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestRAM:
    """RAM read/write and mirroring tests."""

    def test_ram_read_write(self) -> None:
        """Basic RAM read/write at $0000."""
        bus = Bus()
        bus.write(0x0000, 0xAB)
        assert bus.read(0x0000) == 0xAB

    def test_ram_mirror_0800(self) -> None:
        """$0800 mirrors $0000 — writing to one reads from the other."""
        bus = Bus()
        bus.write(0x0000, 0x42)
        assert bus.read(0x0800) == 0x42

    def test_ram_mirror_1000(self) -> None:
        """$1000 mirrors $0000."""
        bus = Bus()
        bus.write(0x0000, 0x7F)
        assert bus.read(0x1000) == 0x7F

    def test_ram_mirror_boundary(self) -> None:
        """$1FFF maps to the last byte of the physical 2 KB RAM ($07FF)."""
        bus = Bus()
        bus.write(0x07FF, 0xDE)
        assert bus.read(0x1FFF) == 0xDE

    def test_ram_mirror_1800(self) -> None:
        """$1800 mirrors $0000 (third mirror)."""
        bus = Bus()
        bus.write(0x0000, 0x33)
        assert bus.read(0x1800) == 0x33


class TestPPURegisterRouting:
    """PPU register read/write routing tests."""

    def test_ppu_register_read(self) -> None:
        """$2000 routes to PPU cpu_read."""
        ppu = MockPPU()
        bus = Bus(ppu=ppu)
        result = bus.read(0x2000)
        assert result == 0x42
        assert ppu.read_log == [0x2000]

    def test_ppu_register_mirror(self) -> None:
        """$3FF8 mirrors $2000 (last mirror in the 8 KB PPU register region)."""
        ppu = MockPPU()
        bus = Bus(ppu=ppu)
        result = bus.read(0x3FF8)
        assert result == 0x42
        assert ppu.read_log == [0x2000]

    def test_ppu_register_write(self) -> None:
        """$2001 write routes to PPU cpu_write."""
        ppu = MockPPU()
        bus = Bus(ppu=ppu)
        bus.write(0x2001, 0x1F)
        assert ppu.write_log == [(0x2001, 0x1F)]

    def test_ppu_register_mirror_write(self) -> None:
        """Write to mirrored PPU register address routes correctly."""
        ppu = MockPPU()
        bus = Bus(ppu=ppu)
        bus.write(0x2009, 0xAB)  # mirror of $2001
        assert ppu.write_log == [(0x2001, 0xAB)]


class TestOAMDMA:
    """OAM DMA ($4014) tests."""

    def test_oam_dma(self) -> None:
        """Writing to $4014 triggers OAM DMA."""
        ppu = MockPPU()
        bus = Bus(ppu=ppu)
        # Write a page number (e.g. 0x02 → base address $0200)
        bus.write(0x4014, 0x02)
        # 256 bytes should have been copied
        assert len(ppu.oam_log) == 256

    def test_oam_dma_copies_256_bytes(self) -> None:
        """OAM DMA copies exactly 256 bytes in order (0-255)."""
        ppu = MockPPU()
        bus = Bus(ppu=ppu)
        # Write a known pattern into RAM at $0300-$03FF
        for i in range(256):
            bus.write(0x0300 + i, i & 0xFF)
        # Trigger DMA from page $03
        bus.write(0x4014, 0x03)
        assert len(ppu.oam_log) == 256
        # Verify each byte was written to the correct OAM address
        for i in range(256):
            expected_addr = i
            expected_value = i & 0xFF
            assert ppu.oam_log[i] == (expected_addr, expected_value)

    def test_oam_dma_uses_cpu_memory(self) -> None:
        """OAM DMA reads from CPU memory space (not a separate bus)."""
        ppu = MockPPU()
        bus = Bus(ppu=ppu)
        # Set up RAM at $0400 to contain $AB every byte
        for i in range(256):
            bus.write(0x0400 + i, 0xAB)
        bus.write(0x4014, 0x04)
        assert all(value == 0xAB for (_addr, value) in ppu.oam_log)


class TestControllerRouting:
    """Controller ($4016, $4017) routing tests."""

    def test_controller_read(self) -> None:
        """$4016 read routes to Controller."""
        ctrl = MockController()
        bus = Bus(controller=ctrl)
        result = bus.read(0x4016)
        assert result == 0x55
        assert len(ctrl.read_log) == 1

    def test_controller_write(self) -> None:
        """$4016 write routes to Controller."""
        ctrl = MockController()
        bus = Bus(controller=ctrl)
        bus.write(0x4016, 1)
        assert ctrl.write_log == [1]


class TestCartridgeRouting:
    """Cartridge space ($4020-$FFFF) routing tests."""

    def test_cartridge_read(self) -> None:
        """$8000 read routes to Cartridge."""
        cart = MockCartridge()
        bus = Bus(cartridge=cart)
        result = bus.read(0x8000)
        assert result == (0x8000 & 0xFF) ^ 0xAA
        assert cart.read_log == [0x8000]

    def test_cartridge_read_boundary(self) -> None:
        """$4020 (lowest cartridge address) routes to Cartridge."""
        cart = MockCartridge()
        bus = Bus(cartridge=cart)
        result = bus.read(0x4020)
        assert cart.read_log == [0x4020]
        assert result == (0x4020 & 0xFF) ^ 0xAA

    def test_cartridge_write(self) -> None:
        """$8000 write routes to Cartridge."""
        cart = MockCartridge()
        bus = Bus(cartridge=cart)
        bus.write(0x8000, 0xEF)
        assert cart.write_log == [(0x8000, 0xEF)]


class TestAPURange:
    """APU / I/O range returns 0 for unimplemented addresses."""

    def test_apu_range_returns_zero(self) -> None:
        """$4000-$4015 returns 0 (APU not implemented)."""
        bus = Bus()
        assert bus.read(0x4000) == 0
        assert bus.read(0x4005) == 0
        assert bus.read(0x4015) == 0

    def test_apu_test_range_returns_zero(self) -> None:
        """$4018-$401F returns 0."""
        bus = Bus()
        assert bus.read(0x4018) == 0
        assert bus.read(0x401F) == 0

    def test_controller_two_returns_zero(self) -> None:
        """$4017 always returns 0 (controller 2 not implemented)."""
        bus = Bus()
        assert bus.read(0x4017) == 0


class TestValueClamping:
    """Value clamping and edge cases."""

    def test_write_value_clamped(self) -> None:
        """Values written are clamped to 8 bits (0-255)."""
        bus = Bus()
        bus.write(0x0000, 0x1FF)  # only low byte should be written
        assert bus.read(0x0000) == 0xFF

    def test_none_devices_dont_crash(self) -> None:
        """Bus works correctly when optional devices are None."""
        bus = Bus()  # no ppu, cartridge, or controller

        # RAM should still work
        bus.write(0x0000, 0x42)
        assert bus.read(0x0000) == 0x42

        # PPU region returns 0 without a PPU
        assert bus.read(0x2000) == 0

        # Cartridge region returns 0 without a cartridge
        assert bus.read(0x8000) == 0

        # Controller returns 0 without a controller
        assert bus.read(0x4016) == 0

        # OAM DMA does nothing without a PPU (no crash)
        bus.write(0x4014, 0x02)

    def test_address_wraps_16bit(self) -> None:
        """Addresses are masked to 16 bits."""
        bus = Bus()
        bus.write(0x10000, 0xCD)  # equivalent to $0000
        assert bus.read(0x0000) == 0xCD

    def test_oam_dma_no_ppu(self) -> None:
        """OAM DMA without a PPU does not crash."""
        bus = Bus()  # ppu=None
        bus.write(0x4014, 0x01)  # should not raise
