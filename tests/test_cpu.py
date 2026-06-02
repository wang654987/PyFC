"""Unit tests for CPU6502 using MemoryStub instead of a real Bus."""

from __future__ import annotations

import pytest

from src.cpu import CPU6502


class MemoryStub:
    """Simulated memory for CPU unit testing without a real Bus."""

    def __init__(self) -> None:
        """Create an empty memory stub."""
        self.memory: dict[int, int] = {}

    def read(self, address: int) -> int:
        """Read a byte from *address*, returning 0 for unmapped locations."""
        return self.memory.get(address & 0xFFFF, 0)

    def write(self, address: int, value: int) -> None:
        """Write *value* to *address*."""
        self.memory[address & 0xFFFF] = value & 0xFF

    def load_program(self, start_addr: int, data: list[int]) -> None:
        """Load a sequence of bytes at *start_addr*."""
        for i, b in enumerate(data):
            self.memory[start_addr + i] = b & 0xFF


# ── Fixture ────────────────────────────────────────────────────────


@pytest.fixture
def cpu() -> CPU6502:
    """Create a fresh CPU instance wired to a fresh MemoryStub."""
    mem = MemoryStub()
    cpu = CPU6502(mem)  # type: ignore[arg-type]
    cpu.pc = 0x8000
    return cpu


# ═══════════════════════════════════════════════════════════════════
#  Addressing mode tests
# ═══════════════════════════════════════════════════════════════════


class TestAddressingModes:
    """Tests for the 13 addressing modes."""

    def test_immediate_addressing(self, cpu: CPU6502) -> None:
        """LDA #$42 → A = $42."""
        cpu.bus.load_program(0x8000, [0xA9, 0x42])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x42
        assert cpu.pc == 0x8002

    def test_zero_page_addressing(self, cpu: CPU6502) -> None:
        """LDA $10 with $10=0x42 → A = $42."""
        cpu.bus.write(0x10, 0x42)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xA5, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x42

    def test_zero_page_x_addressing(self, cpu: CPU6502) -> None:
        """LDA $10,X with X=5, $15=0x42 → A = $42."""
        cpu.x = 5
        cpu.bus.write(0x15, 0x42)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xB5, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x42

    def test_zero_page_wraparound(self, cpu: CPU6502) -> None:
        """ZP+X wraps within zero page ($FF + 5 → $04)."""
        cpu.x = 5
        cpu.bus.write(0x04, 0x77)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xB5, 0xFF])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x77

    def test_absolute_addressing(self, cpu: CPU6502) -> None:
        """LDA $1234 → A loaded from absolute address."""
        cpu.bus.write(0x1234, 0x88)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xAD, 0x34, 0x12])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x88

    def test_absolute_x_cross_page(self, cpu: CPU6502) -> None:
        """ABS+X crossing page adds 1 extra cycle."""
        cpu.x = 0x80
        addr_base = 0x81C0  # 0x81C0 + 0x80 = 0x8240 → crosses from $81 to $82
        target = (addr_base + cpu.x) & 0xFFFF  # 0x8240
        cpu.bus.write(target, 0x55)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xBD, addr_base & 0xFF, addr_base >> 8])  # type: ignore[attr-defined]
        cycles = cpu.step()
        # base=4, cross-page=+1 → 5
        assert cycles == 5
        assert cpu.a == 0x55

    def test_indirect_x_addressing(self, cpu: CPU6502) -> None:
        """LDA ($10,X) with X=4: pointer at ($14,$15) → $2040."""
        cpu.x = 4
        # pointer at $14,$15: $14=0x40, $15=0x20 → address $2040
        cpu.bus.write(0x14, 0x40)  # type: ignore[attr-defined]
        cpu.bus.write(0x15, 0x20)  # type: ignore[attr-defined]
        cpu.bus.write(0x2040, 0x99)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xA1, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x99

    def test_indirect_y_addressing(self, cpu: CPU6502) -> None:
        """LDA ($10),Y: pointer at ($10,$11) = $2000, Y=5 → $2005."""
        cpu.y = 5
        cpu.bus.write(0x10, 0x00)  # type: ignore[attr-defined]
        cpu.bus.write(0x11, 0x20)  # type: ignore[attr-defined]
        cpu.bus.write(0x2005, 0xAB)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xB1, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0xAB

    def test_jmp_indirect_bug(self, cpu: CPU6502) -> None:
        """JMP ($02FF) reads high byte from $0200 (6502 page-boundary bug)."""
        # pointer at $02FF-$0200: lo from $02FF, hi from $0200
        cpu.bus.write(0x02FF, 0x34)  # type: ignore[attr-defined]
        cpu.bus.write(0x0200, 0x12)  # type: ignore[attr-defined]
        # Note: $0300 should NOT be used (that would be correct behavior without the bug)
        cpu.bus.write(0x0300, 0x99)  # type: ignore[attr-defined]  # should be ignored
        cpu.bus.load_program(0x8000, [0x6C, 0xFF, 0x02])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x1234

    def test_relative_forward(self, cpu: CPU6502) -> None:
        """BEQ with Z=1 → branch forward."""
        cpu._set_flag(cpu.Z_FLAG, True)
        cpu.bus.load_program(0x8000, [0xF0, 0x05])  # type: ignore[attr-defined]
        cycles = cpu.step()
        # base=2, taken=+1, same-page → 3
        assert cycles == 3
        assert cpu.pc == 0x8002 + 5

    def test_relative_backward(self, cpu: CPU6502) -> None:
        """BNE with Z=0 → branch backward."""
        cpu._set_flag(cpu.Z_FLAG, False)
        # offset 0xFB = -5; 0x8002 - 5 = 0x7FFD → crosses from page $80 to $7F
        cpu.bus.load_program(0x8000, [0xD0, 0xFB])  # type: ignore[attr-defined]
        cycles = cpu.step()
        assert cycles == 4  # base=2, taken=+1, cross-page=+1
        assert cpu.pc == 0x8002 - 5  # = 0x7FFD

    def test_relative_cross_page(self, cpu: CPU6502) -> None:
        """Branch that crosses a page boundary adds 2 extra cycles."""
        cpu._set_flag(cpu.Z_FLAG, True)
        cpu.pc = 0x80FE
        # offset 0x05 → target = 0x8100 + 0x05 = 0x8105 → crossed page
        cpu.bus.write(0x80FE, 0xF0)  # type: ignore[attr-defined]
        cpu.bus.write(0x80FF, 0x05)  # type: ignore[attr-defined]
        cpu.step()
        # base=2, taken+cross-page=+2 → 4
        # pc = 0x80FF + 1 + 5 = 0x8105
        assert cpu.pc == 0x8105


# ═══════════════════════════════════════════════════════════════════
#  Arithmetic instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestArithmetic:
    """Tests for ADC, SBC, INC, DEC, INX, DEX, INY, DEY."""

    def test_adc_no_carry(self, cpu: CPU6502) -> None:
        """ADC #$10 with A=$20, C=0 → A=$30, C=0, Z=0, N=0."""
        cpu.a = 0x20
        cpu.bus.load_program(0x8000, [0x69, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x30
        assert cpu._get_flag(cpu.C_FLAG) == 0
        assert cpu._get_flag(cpu.Z_FLAG) == 0
        assert cpu._get_flag(cpu.N_FLAG) == 0

    def test_adc_with_carry(self, cpu: CPU6502) -> None:
        """ADC #$01 with A=$FF, C=1 → A=$01, C=1, Z=0, N=0.

        $FF + $01 + 1 (carry) = $101 → A=$01, C=1.
        """
        cpu.a = 0xFF
        cpu._set_flag(cpu.C_FLAG, True)
        cpu.bus.load_program(0x8000, [0x69, 0x01])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x01
        assert cpu._get_flag(cpu.C_FLAG) == 1
        assert cpu._get_flag(cpu.Z_FLAG) == 0
        assert cpu._get_flag(cpu.N_FLAG) == 0

    def test_adc_overflow(self, cpu: CPU6502) -> None:
        """ADC: 0x40 + 0x40 = 0x80 → V=1 (64+64=128, overflow)."""
        cpu.a = 0x40
        cpu.bus.load_program(0x8000, [0x69, 0x40])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x80
        assert cpu._get_flag(cpu.V_FLAG) == 1

    def test_adc_overflow_no(self, cpu: CPU6502) -> None:
        """ADC: 0x40 + 0x20 = 0x60 → V=0 (no overflow)."""
        cpu.a = 0x40
        cpu.bus.load_program(0x8000, [0x69, 0x20])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x60
        assert cpu._get_flag(cpu.V_FLAG) == 0

    def test_sbc_no_borrow(self, cpu: CPU6502) -> None:
        """SBC #$10 with A=$30, C=1 → A=$20, C=1, Z=0."""
        cpu.a = 0x30
        cpu._set_flag(cpu.C_FLAG, True)
        cpu.bus.load_program(0x8000, [0xE9, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x20
        assert cpu._get_flag(cpu.C_FLAG) == 1

    def test_sbc_with_borrow(self, cpu: CPU6502) -> None:
        """SBC #$01 with A=$00, C=1 → A=$FF, C=0 (borrow)."""
        cpu.a = 0x00
        cpu._set_flag(cpu.C_FLAG, True)  # no borrow
        cpu.bus.load_program(0x8000, [0xE9, 0x01])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0xFF
        assert cpu._get_flag(cpu.C_FLAG) == 0  # borrow occurred
        assert cpu._get_flag(cpu.N_FLAG) == 1

    def test_sbc_overflow(self, cpu: CPU6502) -> None:
        """SBC: 0x50 - 0xB0 with C=1 → 0xA0, V=1 (80-(-80)=160, overflow)."""
        cpu.a = 0x50
        cpu._set_flag(cpu.C_FLAG, True)
        cpu.bus.load_program(0x8000, [0xE9, 0xB0])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0xA0
        assert cpu._get_flag(cpu.V_FLAG) == 1

    def test_inc_zero_page(self, cpu: CPU6502) -> None:
        """INC $10 increments memory at $10."""
        cpu.bus.write(0x10, 0x05)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xE6, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.bus.read(0x10) == 0x06  # type: ignore[attr-defined]
        assert cpu._get_flag(cpu.Z_FLAG) == 0

    def test_inc_wraps_to_zero(self, cpu: CPU6502) -> None:
        """INC $10 from $FF → $00, Z=1."""
        cpu.bus.write(0x10, 0xFF)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0xE6, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.bus.read(0x10) == 0x00  # type: ignore[attr-defined]
        assert cpu._get_flag(cpu.Z_FLAG) == 1

    def test_inx(self, cpu: CPU6502) -> None:
        """INX increments X and sets Z/N."""
        cpu.x = 0x7F
        cpu.bus.load_program(0x8000, [0xE8])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.x == 0x80
        assert cpu._get_flag(cpu.N_FLAG) == 1
        assert cpu._get_flag(cpu.Z_FLAG) == 0

    def test_dex_wraps_to_zero(self, cpu: CPU6502) -> None:
        """DEX from X=$01 → X=$00, Z=1."""
        cpu.x = 0x01
        cpu.bus.load_program(0x8000, [0xCA])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.x == 0x00
        assert cpu._get_flag(cpu.Z_FLAG) == 1

    def test_iny(self, cpu: CPU6502) -> None:
        """INY increments Y and sets flags."""
        cpu.y = 0x00
        cpu.bus.load_program(0x8000, [0xC8])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.y == 0x01
        assert cpu._get_flag(cpu.Z_FLAG) == 0

    def test_dey(self, cpu: CPU6502) -> None:
        """DEY decrements Y and sets flags."""
        cpu.y = 0x00
        cpu.bus.load_program(0x8000, [0x88])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.y == 0xFF
        assert cpu._get_flag(cpu.N_FLAG) == 1


# ═══════════════════════════════════════════════════════════════════
#  Logical instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestLogical:
    """Tests for AND, ORA, EOR, BIT."""

    def test_and_zero(self, cpu: CPU6502) -> None:
        """AND #$00 clears A and sets Z."""
        cpu.a = 0xFF
        cpu.bus.load_program(0x8000, [0x29, 0x00])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x00
        assert cpu._get_flag(cpu.Z_FLAG) == 1

    def test_ora_set_bits(self, cpu: CPU6502) -> None:
        """ORA #$0F with A=$F0 → A=$FF."""
        cpu.a = 0xF0
        cpu.bus.load_program(0x8000, [0x09, 0x0F])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0xFF
        assert cpu._get_flag(cpu.N_FLAG) == 1

    def test_eor_toggle(self, cpu: CPU6502) -> None:
        """EOR #$FF toggles all bits: $0F → $F0."""
        cpu.a = 0x0F
        cpu.bus.load_program(0x8000, [0x49, 0xFF])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0xF0

    def test_bit_zero_flag(self, cpu: CPU6502) -> None:
        """BIT sets Z flag when A & mem == 0."""
        cpu.a = 0x0F
        # byte at $10: bit pattern 0xF0 (no overlap with 0x0F)
        cpu.bus.write(0x10, 0xF0)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0x24, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.Z_FLAG) == 1
        # N = bit7 of memory = 1
        assert cpu._get_flag(cpu.N_FLAG) == 1
        # V = bit6 of memory = 1 (0xF0 has bit 7=1, bit 6=1)
        assert cpu._get_flag(cpu.V_FLAG) == 1

    def test_bit_nv_flags(self, cpu: CPU6502) -> None:
        """BIT copies memory bit7→N, bit6→V."""
        cpu.a = 0xFF  # ensure Z=0
        cpu.bus.write(0x10, 0x40)  # type: ignore[attr-defined]  # bit6=1, bit7=0
        cpu.bus.load_program(0x8000, [0x24, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.Z_FLAG) == 0
        assert cpu._get_flag(cpu.N_FLAG) == 0
        assert cpu._get_flag(cpu.V_FLAG) == 1


# ═══════════════════════════════════════════════════════════════════
#  Shift instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestShifts:
    """Tests for ASL, LSR, ROL, ROR."""

    def test_asl_accumulator(self, cpu: CPU6502) -> None:
        """ASL A: shift left, bit7→C, bit0←0."""
        cpu.a = 0x81  # 10000001
        cpu.bus.load_program(0x8000, [0x0A])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x02
        assert cpu._get_flag(cpu.C_FLAG) == 1  # bit7 was 1

    def test_lsr_accumulator(self, cpu: CPU6502) -> None:
        """LSR A: shift right, bit0→C, bit7←0."""
        cpu.a = 0x03  # 00000011
        cpu.bus.load_program(0x8000, [0x4A])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x01
        assert cpu._get_flag(cpu.C_FLAG) == 1  # bit0 was 1

    def test_rol_through_carry(self, cpu: CPU6502) -> None:
        """ROL A: rotate left through carry."""
        cpu.a = 0x80  # 10000000
        cpu._set_flag(cpu.C_FLAG, True)
        cpu.bus.load_program(0x8000, [0x2A])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x01  # shifted left, carry→bit0
        assert cpu._get_flag(cpu.C_FLAG) == 1  # old bit7=1 → carry

    def test_ror_through_carry(self, cpu: CPU6502) -> None:
        """ROR A: rotate right through carry."""
        cpu.a = 0x01  # 00000001
        cpu._set_flag(cpu.C_FLAG, True)
        cpu.bus.load_program(0x8000, [0x6A])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x80  # shifted right, carry→bit7
        assert cpu._get_flag(cpu.C_FLAG) == 1  # old bit0=1 → carry

    def test_asl_memory(self, cpu: CPU6502) -> None:
        """ASL $10 in memory."""
        cpu.bus.write(0x10, 0x40)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0x06, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.bus.read(0x10) == 0x80  # type: ignore[attr-defined]
        assert cpu._get_flag(cpu.C_FLAG) == 0

    def test_lsr_memory(self, cpu: CPU6502) -> None:
        """LSR $10 in memory."""
        cpu.bus.write(0x10, 0x02)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0x46, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.bus.read(0x10) == 0x01  # type: ignore[attr-defined]
        assert cpu._get_flag(cpu.C_FLAG) == 0


# ═══════════════════════════════════════════════════════════════════
#  Branch instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestBranches:
    """Tests for conditional branch instructions."""

    def test_beq_when_zero(self, cpu: CPU6502) -> None:
        """BEQ branches when Z=1."""
        cpu._set_flag(cpu.Z_FLAG, True)
        cpu.bus.write(0x8000, 0xF0)  # type: ignore[attr-defined]
        cpu.bus.write(0x8001, 0x04)  # type: ignore[attr-defined]
        cycles = cpu.step()
        assert cpu.pc == 0x8002 + 4
        assert cycles == 3  # base=2 + taken=1

    def test_beq_when_not_zero(self, cpu: CPU6502) -> None:
        """BEQ does NOT branch when Z=0."""
        cpu._set_flag(cpu.Z_FLAG, False)
        cpu.bus.write(0x8000, 0xF0)  # type: ignore[attr-defined]
        cpu.bus.write(0x8001, 0x04)  # type: ignore[attr-defined]
        cycles = cpu.step()
        assert cpu.pc == 0x8002  # not taken
        assert cycles == 2  # base only

    def test_bne_when_not_zero(self, cpu: CPU6502) -> None:
        """BNE branches when Z=0."""
        cpu._set_flag(cpu.Z_FLAG, False)
        cpu.bus.write(0x8000, 0xD0)  # type: ignore[attr-defined]
        cpu.bus.write(0x8001, 0x06)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x8002 + 6

    def test_bcc_carry_clear(self, cpu: CPU6502) -> None:
        """BCC branches when C=0."""
        cpu._set_flag(cpu.C_FLAG, False)
        cpu.bus.write(0x8000, 0x90)  # type: ignore[attr-defined]
        cpu.bus.write(0x8001, 0x03)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x8002 + 3

    def test_bcs_carry_set(self, cpu: CPU6502) -> None:
        """BCS branches when C=1."""
        cpu._set_flag(cpu.C_FLAG, True)
        cpu.bus.write(0x8000, 0xB0)  # type: ignore[attr-defined]
        cpu.bus.write(0x8001, 0x03)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x8002 + 3

    def test_bmi_negative(self, cpu: CPU6502) -> None:
        """BMI branches when N=1."""
        cpu._set_flag(cpu.N_FLAG, True)
        cpu.bus.write(0x8000, 0x30)  # type: ignore[attr-defined]
        cpu.bus.write(0x8001, 0x02)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x8002 + 2

    def test_bpl_positive(self, cpu: CPU6502) -> None:
        """BPL branches when N=0."""
        cpu._set_flag(cpu.N_FLAG, False)
        cpu.bus.write(0x8000, 0x10)  # type: ignore[attr-defined]
        cpu.bus.write(0x8001, 0x02)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x8002 + 2


# ═══════════════════════════════════════════════════════════════════
#  Stack operation tests
# ═══════════════════════════════════════════════════════════════════


class TestStack:
    """Tests for PHA, PLA, PHP, PLP, JSR, RTS, RTI, TXS, TSX."""

    def test_push_pull(self, cpu: CPU6502) -> None:
        """PHA then PLA preserves the accumulator value."""
        cpu.a = 0x42
        # PHA
        cpu.bus.write(0x8000, 0x48)  # type: ignore[attr-defined]
        cpu.step()
        # PLA
        cpu.a = 0x00  # clear A
        cpu.pc = 0x8001
        cpu.bus.write(0x8001, 0x68)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x42

    def test_jsr_rts(self, cpu: CPU6502) -> None:
        """JSR pushes return address; RTS returns correctly."""
        # JSR $9000
        cpu.bus.load_program(0x8000, [0x20, 0x00, 0x90])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x9000
        assert cpu.sp == 0xFD - 2  # pushed 2 bytes

        # Place RTS at $9000
        cpu.bus.write(0x9000, 0x60)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x8003  # return to next instruction after JSR

    def test_rti_restore(self, cpu: CPU6502) -> None:
        """RTI restores status and PC from stack."""
        # Manually push status=0x83 (NZC set) and PC=0x9000
        cpu.sp = 0xFD
        cpu._push_word(0x9000)
        cpu._push(0x83)
        # RTI
        cpu.bus.write(0x8000, 0x40)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x9000
        assert cpu.status == 0x83

    def test_php_plp(self, cpu: CPU6502) -> None:
        """PHP pushes status; PLP restores it."""
        cpu.status = 0x65  # C=1, Z=0, I=1, D=0, B=0, V=1, N=0
        cpu.bus.write(0x8000, 0x08)  # type: ignore[attr-defined]  # PHP
        cpu.step()
        # Verify pushed value on stack (the stack byte just below 0x01FD)
        pushed = cpu.bus.read(0x0100 | ((cpu.sp + 1) & 0xFF))  # type: ignore[attr-defined]
        # PHP sets B=1 in the pushed byte
        assert (pushed & 0x10) != 0  # B flag set in pushed value

        # Clear status and PLP
        cpu.status = 0x00
        cpu.pc = 0x8001
        cpu.bus.write(0x8001, 0x28)  # type: ignore[attr-defined]  # PLP
        cpu.step()
        # Restored status has B=1 (from PHP push)
        assert (cpu.status & 0x10) != 0

    def test_tsx(self, cpu: CPU6502) -> None:
        """TSX transfers SP to X with Z/N flags."""
        cpu.sp = 0x00
        cpu.bus.write(0x8000, 0xBA)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.x == 0x00
        assert cpu._get_flag(cpu.Z_FLAG) == 1

    def test_txs(self, cpu: CPU6502) -> None:
        """TXS transfers X to SP (no flag changes)."""
        cpu.x = 0xFF
        cpu.bus.write(0x8000, 0x9A)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.sp == 0xFF  # SP unchanged by flags


# ═══════════════════════════════════════════════════════════════════
#  Interrupt tests
# ═══════════════════════════════════════════════════════════════════


class TestInterrupts:
    """Tests for reset, NMI, IRQ, BRK."""

    def test_reset_vector(self, cpu: CPU6502) -> None:
        """reset() reads the reset vector from $FFFC-$FFFD."""
        cpu.bus.write(0xFFFC, 0x00)  # type: ignore[attr-defined]
        cpu.bus.write(0xFFFD, 0x90)  # type: ignore[attr-defined]
        cpu.reset()
        assert cpu.pc == 0x9000
        assert cpu.sp == 0xFD
        assert cpu.status == 0x24  # I + U flags

    def test_nmi_saves_context(self, cpu: CPU6502) -> None:
        """NMI pushes PC and status, then jumps to NMI vector."""
        old_pc = 0x8123
        cpu.pc = old_pc
        cpu.status = 0x05  # C=1, Z=0 (arbitrary)
        cpu.bus.write(0xFFFA, 0x00)  # type: ignore[attr-defined]
        cpu.bus.write(0xFFFB, 0xC0)  # type: ignore[attr-defined]
        cpu.nmi()

        # NMI sets _interrupt_type, next step() handles it
        cycles = cpu.step()
        assert cycles == 7
        assert cpu.pc == 0xC000
        assert cpu._get_flag(cpu.I_FLAG) == 1
        # PC and status should be on stack
        cpu.sp = (cpu.sp + 1) & 0xFF  # point to last pushed (status)
        pushed_status = cpu.bus.read(0x0100 | cpu.sp)  # type: ignore[attr-defined]
        assert pushed_status == 0x05  # B flag should be 0 for NMI

    def test_irq_blocked_by_i_flag(self, cpu: CPU6502) -> None:
        """IRQ is ignored when I flag is set."""
        cpu._set_flag(cpu.I_FLAG, True)
        cpu.irq()
        # step() should handle by ignoring and returning 0
        cycles = cpu.step()
        assert cycles == 0  # ignored

    def test_irq_fires_when_i_clear(self, cpu: CPU6502) -> None:
        """IRQ fires when I flag is clear."""
        cpu.pc = 0x8500
        cpu._set_flag(cpu.I_FLAG, False)
        cpu.bus.write(0xFFFE, 0x34)  # type: ignore[attr-defined]
        cpu.bus.write(0xFFFF, 0x12)  # type: ignore[attr-defined]
        cpu.irq()
        cycles = cpu.step()
        assert cycles == 7
        assert cpu.pc == 0x1234
        assert cpu._get_flag(cpu.I_FLAG) == 1

    def test_brk_sets_b_flag(self, cpu: CPU6502) -> None:
        """BRK pushes status with B flag set, jumps to IRQ vector."""
        old_pc = 0x8200
        cpu.pc = old_pc
        cpu.bus.write(0xFFFE, 0x00)  # type: ignore[attr-defined]
        cpu.bus.write(0xFFFF, 0x90)  # type: ignore[attr-defined]
        # BRK is 2 bytes: 0x00 (opcode) + padding byte
        cpu.bus.load_program(0x8200, [0x00, 0x00])  # type: ignore[attr-defined]
        cycles = cpu.step()
        assert cycles == 7
        assert cpu.pc == 0x9000
        assert cpu._get_flag(cpu.I_FLAG) == 1
        # Check that B flag was set in the pushed status
        cpu.sp = (cpu.sp + 1) & 0xFF  # point to last pushed (status)
        pushed_status = cpu.bus.read(0x0100 | cpu.sp)  # type: ignore[attr-defined]
        assert (pushed_status & 0x10) != 0  # B flag set


# ═══════════════════════════════════════════════════════════════════
#  Transfer instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestTransfers:
    """Tests for TAX, TXA, TAY, TYA, TXY."""

    def test_tax_transfer(self, cpu: CPU6502) -> None:
        """TAX: A → X, sets Z/N flags."""
        cpu.a = 0x00
        cpu.bus.write(0x8000, 0xAA)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.x == 0x00
        assert cpu._get_flag(cpu.Z_FLAG) == 1
        assert cpu._get_flag(cpu.N_FLAG) == 0

    def test_tax_negative(self, cpu: CPU6502) -> None:
        """TAX with A=$80 sets N flag."""
        cpu.a = 0x80
        cpu.bus.write(0x8000, 0xAA)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.x == 0x80
        assert cpu._get_flag(cpu.N_FLAG) == 1

    def test_txa(self, cpu: CPU6502) -> None:
        """TXA: X → A with flag update."""
        cpu.x = 0x42
        cpu.bus.write(0x8000, 0x8A)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x42

    def test_tay(self, cpu: CPU6502) -> None:
        """TAY: A → Y."""
        cpu.a = 0x33
        cpu.bus.write(0x8000, 0xA8)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.y == 0x33

    def test_tya(self, cpu: CPU6502) -> None:
        """TYA: Y → A."""
        cpu.y = 0x77
        cpu.bus.write(0x8000, 0x98)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.a == 0x77

    def test_txy(self, cpu: CPU6502) -> None:
        """TXY: X → Y with Z/N flags."""
        cpu.x = 0x88
        cpu.bus.write(0x8000, 0x9B)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.y == 0x88
        assert cpu._get_flag(cpu.N_FLAG) == 1
        assert cpu._get_flag(cpu.Z_FLAG) == 0


# ═══════════════════════════════════════════════════════════════════
#  Flag manipulation tests
# ═══════════════════════════════════════════════════════════════════


class TestFlags:
    """Tests for flag instructions: CLC, SEC, CLI, SEI, CLV, CLD, SED."""

    def test_clc_sec(self, cpu: CPU6502) -> None:
        """CLC clears carry; SEC sets carry."""
        cpu._set_flag(cpu.C_FLAG, True)
        cpu.bus.write(0x8000, 0x18)  # type: ignore[attr-defined]  # CLC
        cpu.step()
        assert cpu._get_flag(cpu.C_FLAG) == 0

        cpu.pc = 0x8001
        cpu.bus.write(0x8001, 0x38)  # type: ignore[attr-defined]  # SEC
        cpu.step()
        assert cpu._get_flag(cpu.C_FLAG) == 1

    def test_cli_sei(self, cpu: CPU6502) -> None:
        """CLI clears interrupt disable; SEI sets it."""
        cpu._set_flag(cpu.I_FLAG, True)
        cpu.bus.write(0x8000, 0x58)  # type: ignore[attr-defined]  # CLI
        cpu.step()
        assert cpu._get_flag(cpu.I_FLAG) == 0

        cpu.pc = 0x8001
        cpu.bus.write(0x8001, 0x78)  # type: ignore[attr-defined]  # SEI
        cpu.step()
        assert cpu._get_flag(cpu.I_FLAG) == 1

    def test_clv(self, cpu: CPU6502) -> None:
        """CLV clears overflow flag."""
        cpu._set_flag(cpu.V_FLAG, True)
        cpu.bus.write(0x8000, 0xB8)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.V_FLAG) == 0

    def test_cld_sed(self, cpu: CPU6502) -> None:
        """CLD clears decimal flag; SED sets it."""
        cpu._set_flag(cpu.D_FLAG, True)
        cpu.bus.write(0x8000, 0xD8)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.D_FLAG) == 0

        cpu.pc = 0x8001
        cpu.bus.write(0x8001, 0xF8)  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.D_FLAG) == 1


# ═══════════════════════════════════════════════════════════════════
#  Load/Store instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestLoadStore:
    """Tests for LDA, LDX, LDY, STA, STX, STY."""

    def test_ldx_immediate(self, cpu: CPU6502) -> None:
        """LDX #$55 → X=$55."""
        cpu.bus.load_program(0x8000, [0xA2, 0x55])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.x == 0x55

    def test_ldy_immediate(self, cpu: CPU6502) -> None:
        """LDY #$AA → Y=$AA."""
        cpu.bus.load_program(0x8000, [0xA0, 0xAA])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.y == 0xAA

    def test_sta_absolute(self, cpu: CPU6502) -> None:
        """STA $1234 stores A to absolute address."""
        cpu.a = 0xAB
        cpu.bus.load_program(0x8000, [0x8D, 0x34, 0x12])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.bus.read(0x1234) == 0xAB  # type: ignore[attr-defined]

    def test_stx_zero_page(self, cpu: CPU6502) -> None:
        """STX $20 stores X to zero page."""
        cpu.x = 0xCD
        cpu.bus.load_program(0x8000, [0x86, 0x20])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.bus.read(0x20) == 0xCD  # type: ignore[attr-defined]

    def test_sty_absolute(self, cpu: CPU6502) -> None:
        """STY $4000 stores Y to absolute address."""
        cpu.y = 0xEF
        cpu.bus.load_program(0x8000, [0x8C, 0x00, 0x40])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.bus.read(0x4000) == 0xEF  # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════════
#  Compare instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestCompare:
    """Tests for CMP, CPX, CPY."""

    def test_cmp_equal(self, cpu: CPU6502) -> None:
        """CMP #$42 with A=$42 → Z=1, C=1."""
        cpu.a = 0x42
        cpu.bus.load_program(0x8000, [0xC9, 0x42])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.Z_FLAG) == 1
        assert cpu._get_flag(cpu.C_FLAG) == 1  # A >= value

    def test_cmp_less(self, cpu: CPU6502) -> None:
        """CMP #$50 with A=$30 → C=0 (A < value)."""
        cpu.a = 0x30
        cpu.bus.load_program(0x8000, [0xC9, 0x50])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.C_FLAG) == 0
        assert cpu._get_flag(cpu.N_FLAG) == 1  # result $30-$50=$E0 negative

    def test_cpx(self, cpu: CPU6502) -> None:
        """CPX #$40 with X=$50 → C=1, Z=0."""
        cpu.x = 0x50
        cpu.bus.load_program(0x8000, [0xE0, 0x40])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.C_FLAG) == 1
        assert cpu._get_flag(cpu.Z_FLAG) == 0

    def test_cpy(self, cpu: CPU6502) -> None:
        """CPY #$80 with Y=$80 → Z=1."""
        cpu.y = 0x80
        cpu.bus.load_program(0x8000, [0xC0, 0x80])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu._get_flag(cpu.Z_FLAG) == 1


# ═══════════════════════════════════════════════════════════════════
#  Jump instruction tests
# ═══════════════════════════════════════════════════════════════════


class TestJumps:
    """Tests for JMP (absolute and indirect)."""

    def test_jmp_absolute(self, cpu: CPU6502) -> None:
        """JMP $4567 jumps to $4567."""
        cpu.bus.load_program(0x8000, [0x4C, 0x67, 0x45])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x4567

    def test_jmp_indirect(self, cpu: CPU6502) -> None:
        """JMP ($1234) reads address from ($1234,$1235)."""
        cpu.bus.write(0x1234, 0x00)  # type: ignore[attr-defined]
        cpu.bus.write(0x1235, 0x90)  # type: ignore[attr-defined]
        cpu.bus.load_program(0x8000, [0x6C, 0x34, 0x12])  # type: ignore[attr-defined]
        cpu.step()
        assert cpu.pc == 0x9000


# ═══════════════════════════════════════════════════════════════════
#  Misc / NOP / cycles tests
# ═══════════════════════════════════════════════════════════════════


class TestMisc:
    """Tests for NOP, cycles accumulation, unknown opcodes."""

    def test_nop(self, cpu: CPU6502) -> None:
        """NOP does nothing except consume 2 cycles and advance PC."""
        old_pc = cpu.pc
        old_cycles = cpu.cycles
        cpu.bus.write(0x8000, 0xEA)  # type: ignore[attr-defined]
        cycles = cpu.step()
        assert cycles == 2
        assert cpu.pc == old_pc + 1
        assert cpu.cycles == old_cycles + 2

    def test_unknown_opcode_is_nop(self, cpu: CPU6502) -> None:
        """Unknown opcode 0xFF should be treated as NOP (2 cycles)."""
        cpu.bus.write(0x8000, 0xFF)  # type: ignore[attr-defined]
        cycles = cpu.step()
        assert cycles == 2
        assert cpu.pc == 0x8001

    def test_cycles_accumulate(self, cpu: CPU6502) -> None:
        """Multiple steps accumulate cycles correctly."""
        # LDA #$01 (2) + STA $10 (3) = 5 cycles
        cpu.bus.load_program(0x8000, [0xA9, 0x01, 0x85, 0x10])  # type: ignore[attr-defined]
        cpu.step()
        cpu.step()
        assert cpu.cycles == 5


# ═══════════════════════════════════════════════════════════════════
#  Opcode coverage verification
# ═══════════════════════════════════════════════════════════════════


class TestOpcodeCoverage:
    """Verify that all 151 official opcodes are registered."""

    def test_all_official_opcodes_present(self, cpu: CPU6502) -> None:
        """Check that all opcodes (151 official + TXY = 152) are in the table."""
        official_opcodes: set[int] = {
            # ADC
            0x69, 0x65, 0x75, 0x6D, 0x7D, 0x79, 0x61, 0x71,
            # AND
            0x29, 0x25, 0x35, 0x2D, 0x3D, 0x39, 0x21, 0x31,
            # ASL
            0x0A, 0x06, 0x16, 0x0E, 0x1E,
            # BCC
            0x90,
            # BCS
            0xB0,
            # BEQ
            0xF0,
            # BIT
            0x24, 0x2C,
            # BMI
            0x30,
            # BNE
            0xD0,
            # BPL
            0x10,
            # BRK
            0x00,
            # BVC
            0x50,
            # BVS
            0x70,
            # CLC
            0x18,
            # CLD
            0xD8,
            # CLI
            0x58,
            # CLV
            0xB8,
            # CMP
            0xC9, 0xC5, 0xD5, 0xCD, 0xDD, 0xD9, 0xC1, 0xD1,
            # CPX
            0xE0, 0xE4, 0xEC,
            # CPY
            0xC0, 0xC4, 0xCC,
            # DEC
            0xC6, 0xD6, 0xCE, 0xDE,
            # DEX
            0xCA,
            # DEY
            0x88,
            # EOR
            0x49, 0x45, 0x55, 0x4D, 0x5D, 0x59, 0x41, 0x51,
            # INC
            0xE6, 0xF6, 0xEE, 0xFE,
            # INX
            0xE8,
            # INY
            0xC8,
            # JMP
            0x4C, 0x6C,
            # JSR
            0x20,
            # LDA
            0xA9, 0xA5, 0xB5, 0xAD, 0xBD, 0xB9, 0xA1, 0xB1,
            # LDX
            0xA2, 0xA6, 0xB6, 0xAE, 0xBE,
            # LDY
            0xA0, 0xA4, 0xB4, 0xAC, 0xBC,
            # LSR
            0x4A, 0x46, 0x56, 0x4E, 0x5E,
            # NOP
            0xEA,
            # ORA
            0x09, 0x05, 0x15, 0x0D, 0x1D, 0x19, 0x01, 0x11,
            # PHA
            0x48,
            # PHP
            0x08,
            # PLA
            0x68,
            # PLP
            0x28,
            # ROL
            0x2A, 0x26, 0x36, 0x2E, 0x3E,
            # ROR
            0x6A, 0x66, 0x76, 0x6E, 0x7E,
            # RTI
            0x40,
            # RTS
            0x60,
            # SBC
            0xE9, 0xE5, 0xF5, 0xED, 0xFD, 0xF9, 0xE1, 0xF1,
            # SEC
            0x38,
            # SED
            0xF8,
            # SEI
            0x78,
            # STA
            0x85, 0x95, 0x8D, 0x9D, 0x99, 0x81, 0x91,
            # STX
            0x86, 0x96, 0x8E,
            # STY
            0x84, 0x94, 0x8C,
            # TAX
            0xAA,
            # TAY
            0xA8,
            # TSX
            0xBA,
            # TXA
            0x8A,
            # TXS
            0x9A,
            # TXY
            0x9B,
            # TYA
            0x98,
        }

        # _opcode_table is now a list[Instruction] (256 entries).
        # Defined opcodes have non-"NOP" mnemonics or are the real NOP (0xEA).
        defined: set[int] = {
            i
            for i in range(256)
            if cpu._opcode_table[i].mnemonic != "NOP" or i == 0xEA
        }
        missing = official_opcodes - defined
        extra = defined - official_opcodes

        assert not missing, f"Missing opcodes: {[hex(x) for x in sorted(missing)]}"
        assert not extra, f"Extra opcodes in table: {[hex(x) for x in sorted(extra)]}"
        assert len(defined) == 152  # 151 official + TXY (0x9B)
