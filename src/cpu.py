"""MOS 6502 CPU emulator.

Implements all 56 official instructions (151 opcodes), 13 addressing modes,
and full interrupt handling (NMI, IRQ, RESET, BRK).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bus import Bus


@dataclass(slots=True)
class Instruction:
    """Descriptor for a single opcode entry in the instruction table."""

    mnemonic: str
    addressing_mode_fn: Callable[..., tuple[int, bool]]
    operation_fn: Callable[..., int]
    base_cycles: int


class CPU6502:
    """MOS 6502 CPU simulator."""

    # ── Registers ──────────────────────────────────────────────────
    a: int  # Accumulator (0-255)
    x: int  # X index register (0-255)
    y: int  # Y index register (0-255)
    sp: int  # Stack pointer (0-255), actual address = 0x0100 + sp
    pc: int  # Program counter (0-65535)
    status: int  # Status register (8 bits)
    cycles: int  # Total elapsed cycles

    # ── Flag bit positions ─────────────────────────────────────────
    C_FLAG: int = 0  # Carry
    Z_FLAG: int = 1  # Zero
    I_FLAG: int = 2  # Interrupt Disable
    D_FLAG: int = 3  # Decimal mode (not used on NES)
    B_FLAG: int = 4  # Break (BRK instruction)
    U_FLAG: int = 5  # Unused (usually 1)
    V_FLAG: int = 6  # Overflow
    N_FLAG: int = 7  # Negative

    def __init__(self, bus: Bus) -> None:
        """Create a new CPU instance connected to *bus*."""
        self.bus = bus
        # Cache bus method references for hot-path performance
        self._bus_read = bus.read
        self._bus_write = bus.write
        self.a = 0
        self.x = 0
        self.y = 0
        self.sp = 0xFD
        self.pc = 0x0000
        self.status = 0x24  # I flag + unused flag set
        self.cycles = 0
        self._interrupt_type: int = 0  # 0=none, 1=NMI, 2=IRQ
        self._opcode_table: list[Instruction] = self._build_opcode_table()

    # ── Bus I/O helpers ────────────────────────────────────────────

    def _read(self, address: int) -> int:
        """Read a byte through the bus."""
        return self._bus_read(address & 0xFFFF)

    def _write(self, address: int, value: int) -> None:
        """Write a byte through the bus."""
        self._bus_write(address & 0xFFFF, value & 0xFF)

    def _read_word(self, address: int) -> int:
        """Read a 16-bit little-endian word."""
        lo = self._read(address)
        hi = self._read((address + 1) & 0xFFFF)
        return lo | (hi << 8)

    # ── Flag helpers ───────────────────────────────────────────────

    def _get_flag(self, flag: int) -> int:
        """Get the value of a flag (0 or 1)."""
        return (self.status >> flag) & 1

    def _set_flag(self, flag: int, value: bool | int) -> None:
        """Set or clear a flag."""
        if value:
            self.status |= 1 << flag
        else:
            self.status &= ~(1 << flag)

    # ── Stack operations ───────────────────────────────────────────

    def _push(self, value: int) -> None:
        """Push a byte onto the stack at 0x0100+SP, then decrement SP."""
        self._write(0x0100 | self.sp, value & 0xFF)
        self.sp = (self.sp - 1) & 0xFF

    def _pull(self) -> int:
        """Increment SP, then pull a byte from the stack at 0x0100+SP."""
        self.sp = (self.sp + 1) & 0xFF
        return self._read(0x0100 | self.sp)

    def _push_word(self, value: int) -> None:
        """Push a 16-bit value onto the stack (high byte first)."""
        self._push((value >> 8) & 0xFF)
        self._push(value & 0xFF)

    # ── Helper: set Z/N flags based on a register value ────────────

    def _set_zn(self, value: int) -> None:
        """Set Zero and Negative flags for an 8-bit register value."""
        self._set_flag(self.Z_FLAG, value == 0)
        self._set_flag(self.N_FLAG, (value & 0x80) != 0)

    # ═══════════════════════════════════════════════════════════════
    #  Addressing Modes (13)
    # ═══════════════════════════════════════════════════════════════

    def _addr_imp(self) -> tuple[int, bool]:
        """Implicit — no operand."""
        return 0, False

    def _addr_acc(self) -> tuple[int, bool]:
        """Accumulator — operation on register A."""
        return 0, False

    def _addr_imm(self) -> tuple[int, bool]:
        """Immediate — operand is the byte after the opcode."""
        addr = self.pc
        self.pc = (self.pc + 1) & 0xFFFF
        return addr, False

    def _addr_zp(self) -> tuple[int, bool]:
        """Zero Page — operand in range $00-$FF."""
        addr = self._read(self.pc) & 0xFF
        self.pc = (self.pc + 1) & 0xFFFF
        return addr, False

    def _addr_zpx(self) -> tuple[int, bool]:
        """Zero Page,X — zero-page address plus X register (wraps in page)."""
        base = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return (base + self.x) & 0xFF, False

    def _addr_zpy(self) -> tuple[int, bool]:
        """Zero Page,Y — zero-page address plus Y register (wraps in page)."""
        base = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return (base + self.y) & 0xFF, False

    def _addr_abs(self) -> tuple[int, bool]:
        """Absolute — 16-bit address follows the opcode."""
        addr = self._read_word(self.pc)
        self.pc = (self.pc + 2) & 0xFFFF
        return addr, False

    def _addr_absx(self) -> tuple[int, bool]:
        """Absolute,X — absolute address plus X register, may cross page."""
        base = self._read_word(self.pc)
        self.pc = (self.pc + 2) & 0xFFFF
        addr = (base + self.x) & 0xFFFF
        crossed = (base & 0xFF00) != (addr & 0xFF00)
        return addr, crossed

    def _addr_absy(self) -> tuple[int, bool]:
        """Absolute,Y — absolute address plus Y register, may cross page."""
        base = self._read_word(self.pc)
        self.pc = (self.pc + 2) & 0xFFFF
        addr = (base + self.y) & 0xFFFF
        crossed = (base & 0xFF00) != (addr & 0xFF00)
        return addr, crossed

    def _addr_ind(self) -> tuple[int, bool]:
        """Indirect — JMP ($xxxx) with 6502 page-boundary bug.

        If the pointer address ends in $FF, the high byte is read from
        the *same page* (bit 8 does NOT increment), e.g. JMP ($02FF)
        reads low from $02FF and high from $0200.
        """
        ptr = self._read_word(self.pc)
        self.pc = (self.pc + 2) & 0xFFFF

        lo = self._read(ptr)
        hi = (
            self._read(ptr & 0xFF00)
            if (ptr & 0xFF) == 0xFF
            else self._read(ptr + 1)
        )

        return (hi << 8) | lo, False

    def _addr_izx(self) -> tuple[int, bool]:
        """(Indirect,X) — pre-indexed indirect: ($zp,X)."""
        zp = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        ptr = (zp + self.x) & 0xFF
        lo = self._read(ptr)
        hi = self._read((ptr + 1) & 0xFF)
        return (hi << 8) | lo, False

    def _addr_izy(self) -> tuple[int, bool]:
        """(Indirect),Y — post-indexed indirect: ($zp),Y."""
        zp = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        lo = self._read(zp)
        hi = self._read((zp + 1) & 0xFF)
        base = (hi << 8) | lo
        addr = (base + self.y) & 0xFFFF
        crossed = (base & 0xFF00) != (addr & 0xFF00)
        return addr, crossed

    def _addr_rel(self) -> tuple[int, bool]:
        """Relative — signed 8-bit offset for branch instructions."""
        offset = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        if offset & 0x80:
            offset -= 256
        return offset, False

    # ═══════════════════════════════════════════════════════════════
    #  Branch helper
    # ═══════════════════════════════════════════════════════════════

    def _branch(self, condition: bool, offset: int) -> int:
        """Execute a branch if *condition* is true.

        Returns the number of extra cycles consumed:
        - 0 if branch not taken
        - 1 if branch taken (same page)
        - 2 if branch taken + page crossed
        """
        if not condition:
            return 0
        old_pc = self.pc
        self.pc = (self.pc + offset) & 0xFFFF
        extra = 1
        if (old_pc & 0xFF00) != (self.pc & 0xFF00):
            extra += 1
        return extra

    # ═══════════════════════════════════════════════════════════════
    #  Instruction Implementations (56)
    # ═══════════════════════════════════════════════════════════════

    # ── Load / Store ───────────────────────────────────────────────

    def _op_lda(self, addr: int, crossed_page: bool) -> int:
        self.a = self._read(addr)
        self._set_zn(self.a)
        return 1 if crossed_page else 0

    def _op_ldx(self, addr: int, crossed_page: bool) -> int:
        self.x = self._read(addr)
        self._set_zn(self.x)
        return 1 if crossed_page else 0

    def _op_ldy(self, addr: int, crossed_page: bool) -> int:
        self.y = self._read(addr)
        self._set_zn(self.y)
        return 1 if crossed_page else 0

    def _op_sta(self, addr: int, crossed_page: bool) -> int:
        self._write(addr, self.a)
        return 0  # STA always takes fixed cycles on indexed modes

    def _op_stx(self, addr: int, crossed_page: bool) -> int:
        self._write(addr, self.x)
        return 0

    def _op_sty(self, addr: int, crossed_page: bool) -> int:
        self._write(addr, self.y)
        return 0

    # ── Arithmetic ─────────────────────────────────────────────────

    def _op_adc(self, addr: int, crossed_page: bool) -> int:
        value = self._read(addr)
        carry = self._get_flag(self.C_FLAG)
        result = self.a + value + carry

        self._set_flag(self.C_FLAG, result > 0xFF)
        self._set_flag(self.Z_FLAG, (result & 0xFF) == 0)
        # V: overflow when signs of A and operand are equal but sign of result differs
        self._set_flag(self.V_FLAG, (~(self.a ^ value) & (self.a ^ result)) & 0x80)
        self._set_flag(self.N_FLAG, result & 0x80)

        self.a = result & 0xFF
        return 1 if crossed_page else 0

    def _op_sbc(self, addr: int, crossed_page: bool) -> int:
        value = self._read(addr)
        # SBC: A - value - (1 - C) = A + (~value) + C
        carry = self._get_flag(self.C_FLAG)
        result = self.a + (~value & 0xFF) + carry

        self._set_flag(self.C_FLAG, result > 0xFF)
        self._set_flag(self.Z_FLAG, (result & 0xFF) == 0)
        # V for subtraction: set when signs of A and operand differ AND
        # signs of A and result differ
        self._set_flag(self.V_FLAG, ((self.a ^ result) & (self.a ^ value)) & 0x80)
        self._set_flag(self.N_FLAG, result & 0x80)

        self.a = result & 0xFF
        return 1 if crossed_page else 0

    def _op_inc(self, addr: int, crossed_page: bool) -> int:
        value = (self._read(addr) + 1) & 0xFF
        self._write(addr, value)
        self._set_zn(value)
        return 0

    def _op_inx(self, addr: int, crossed_page: bool) -> int:
        self.x = (self.x + 1) & 0xFF
        self._set_zn(self.x)
        return 0

    def _op_iny(self, addr: int, crossed_page: bool) -> int:
        self.y = (self.y + 1) & 0xFF
        self._set_zn(self.y)
        return 0

    def _op_dec(self, addr: int, crossed_page: bool) -> int:
        value = (self._read(addr) - 1) & 0xFF
        self._write(addr, value)
        self._set_zn(value)
        return 0

    def _op_dex(self, addr: int, crossed_page: bool) -> int:
        self.x = (self.x - 1) & 0xFF
        self._set_zn(self.x)
        return 0

    def _op_dey(self, addr: int, crossed_page: bool) -> int:
        self.y = (self.y - 1) & 0xFF
        self._set_zn(self.y)
        return 0

    # ── Logical ────────────────────────────────────────────────────

    def _op_and(self, addr: int, crossed_page: bool) -> int:
        self.a &= self._read(addr)
        self._set_zn(self.a)
        return 1 if crossed_page else 0

    def _op_ora(self, addr: int, crossed_page: bool) -> int:
        self.a |= self._read(addr)
        self._set_zn(self.a)
        return 1 if crossed_page else 0

    def _op_eor(self, addr: int, crossed_page: bool) -> int:
        self.a ^= self._read(addr)
        self._set_zn(self.a)
        return 1 if crossed_page else 0

    def _op_bit(self, addr: int, crossed_page: bool) -> int:
        value = self._read(addr)
        self._set_flag(self.Z_FLAG, (self.a & value) == 0)
        self._set_flag(self.N_FLAG, value & 0x80)
        self._set_flag(self.V_FLAG, value & 0x40)
        return 0

    # ── Shifts ─────────────────────────────────────────────────────

    def _op_asl(self, addr: int, crossed_page: bool) -> int:
        value = self._read(addr)
        self._set_flag(self.C_FLAG, value & 0x80)
        value = (value << 1) & 0xFF
        self._write(addr, value)
        self._set_zn(value)
        return 0

    def _op_asl_acc(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.C_FLAG, self.a & 0x80)
        self.a = (self.a << 1) & 0xFF
        self._set_zn(self.a)
        return 0

    def _op_lsr(self, addr: int, crossed_page: bool) -> int:
        value = self._read(addr)
        self._set_flag(self.C_FLAG, value & 0x01)
        value >>= 1
        self._write(addr, value)
        self._set_zn(value)
        return 0

    def _op_lsr_acc(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.C_FLAG, self.a & 0x01)
        self.a >>= 1
        self._set_zn(self.a)
        return 0

    def _op_rol(self, addr: int, crossed_page: bool) -> int:
        value = self._read(addr)
        carry_in = self._get_flag(self.C_FLAG)
        old_bit7 = value & 0x80
        value = ((value << 1) | carry_in) & 0xFF
        self._set_flag(self.C_FLAG, old_bit7)
        self._write(addr, value)
        self._set_zn(value)
        return 0

    def _op_rol_acc(self, addr: int, crossed_page: bool) -> int:
        carry_in = self._get_flag(self.C_FLAG)
        old_bit7 = self.a & 0x80
        self.a = ((self.a << 1) | carry_in) & 0xFF
        self._set_flag(self.C_FLAG, old_bit7)
        self._set_zn(self.a)
        return 0

    def _op_ror(self, addr: int, crossed_page: bool) -> int:
        value = self._read(addr)
        carry_in = self._get_flag(self.C_FLAG)
        old_bit0 = value & 0x01
        value = (value >> 1) | (carry_in << 7)
        self._set_flag(self.C_FLAG, old_bit0)
        self._write(addr, value)
        self._set_zn(value)
        return 0

    def _op_ror_acc(self, addr: int, crossed_page: bool) -> int:
        carry_in = self._get_flag(self.C_FLAG)
        old_bit0 = self.a & 0x01
        self.a = (self.a >> 1) | (carry_in << 7)
        self._set_flag(self.C_FLAG, old_bit0)
        self._set_zn(self.a)
        return 0

    # ── Compare ────────────────────────────────────────────────────

    def _compare(self, reg: int, value: int) -> None:
        """Set C, Z, N flags for a comparison (reg - value)."""
        result = reg - value
        self._set_flag(self.C_FLAG, reg >= value)
        self._set_flag(self.Z_FLAG, (result & 0xFF) == 0)
        self._set_flag(self.N_FLAG, result & 0x80)

    def _op_cmp(self, addr: int, crossed_page: bool) -> int:
        self._compare(self.a, self._read(addr))
        return 1 if crossed_page else 0

    def _op_cpx(self, addr: int, crossed_page: bool) -> int:
        self._compare(self.x, self._read(addr))
        return 0

    def _op_cpy(self, addr: int, crossed_page: bool) -> int:
        self._compare(self.y, self._read(addr))
        return 0

    # ── Branch instructions ────────────────────────────────────────

    def _op_bcc(self, addr: int, crossed_page: bool) -> int:
        return self._branch(not self._get_flag(self.C_FLAG), addr)

    def _op_bcs(self, addr: int, crossed_page: bool) -> int:
        return self._branch(bool(self._get_flag(self.C_FLAG)), addr)

    def _op_beq(self, addr: int, crossed_page: bool) -> int:
        return self._branch(bool(self._get_flag(self.Z_FLAG)), addr)

    def _op_bne(self, addr: int, crossed_page: bool) -> int:
        return self._branch(not self._get_flag(self.Z_FLAG), addr)

    def _op_bmi(self, addr: int, crossed_page: bool) -> int:
        return self._branch(bool(self._get_flag(self.N_FLAG)), addr)

    def _op_bpl(self, addr: int, crossed_page: bool) -> int:
        return self._branch(not self._get_flag(self.N_FLAG), addr)

    def _op_bvc(self, addr: int, crossed_page: bool) -> int:
        return self._branch(not self._get_flag(self.V_FLAG), addr)

    def _op_bvs(self, addr: int, crossed_page: bool) -> int:
        return self._branch(bool(self._get_flag(self.V_FLAG)), addr)

    # ── Jump / Subroutine ──────────────────────────────────────────

    def _op_jmp(self, addr: int, crossed_page: bool) -> int:
        self.pc = addr
        return 0

    def _op_jsr(self, addr: int, crossed_page: bool) -> int:
        # Push return address (address of the last byte of JSR = pc - 1)
        self._push_word((self.pc - 1) & 0xFFFF)
        self.pc = addr
        return 0

    def _op_rts(self, addr: int, crossed_page: bool) -> int:
        lo = self._pull()
        hi = self._pull()
        self.pc = (((hi << 8) | lo) + 1) & 0xFFFF
        return 0

    def _op_rti(self, addr: int, crossed_page: bool) -> int:
        self.status = self._pull()
        lo = self._pull()
        hi = self._pull()
        self.pc = (hi << 8) | lo
        return 0

    def _op_brk(self, addr: int, crossed_page: bool) -> int:
        # BRK is a 2-byte instruction: skip the padding byte
        self.pc = (self.pc + 1) & 0xFFFF
        self._push_word(self.pc)
        self._push(self.status | (1 << self.B_FLAG))
        self._set_flag(self.I_FLAG, True)
        self.pc = self._read_word(0xFFFE)
        return 0

    # ── Stack manipulation ─────────────────────────────────────────

    def _op_pha(self, addr: int, crossed_page: bool) -> int:
        self._push(self.a)
        return 0

    def _op_pla(self, addr: int, crossed_page: bool) -> int:
        self.a = self._pull()
        self._set_zn(self.a)
        return 0

    def _op_php(self, addr: int, crossed_page: bool) -> int:
        # PHP pushes status with B flag set
        self._push(self.status | (1 << self.B_FLAG))
        return 0

    def _op_plp(self, addr: int, crossed_page: bool) -> int:
        self.status = self._pull()
        return 0

    def _op_txs(self, addr: int, crossed_page: bool) -> int:
        self.sp = self.x
        return 0

    def _op_tsx(self, addr: int, crossed_page: bool) -> int:
        self.x = self.sp
        self._set_zn(self.x)
        return 0

    # ── Register transfers ─────────────────────────────────────────

    def _op_tax(self, addr: int, crossed_page: bool) -> int:
        self.x = self.a
        self._set_zn(self.x)
        return 0

    def _op_txa(self, addr: int, crossed_page: bool) -> int:
        self.a = self.x
        self._set_zn(self.a)
        return 0

    def _op_tay(self, addr: int, crossed_page: bool) -> int:
        self.y = self.a
        self._set_zn(self.y)
        return 0

    def _op_tya(self, addr: int, crossed_page: bool) -> int:
        self.a = self.y
        self._set_zn(self.a)
        return 0

    def _op_txy(self, addr: int, crossed_page: bool) -> int:
        """TXY — Transfer X to Y (unofficial but commonly used)."""
        self.y = self.x
        self._set_zn(self.y)
        return 0

    # ── Flag manipulation ──────────────────────────────────────────

    def _op_clc(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.C_FLAG, False)
        return 0

    def _op_sec(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.C_FLAG, True)
        return 0

    def _op_cli(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.I_FLAG, False)
        return 0

    def _op_sei(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.I_FLAG, True)
        return 0

    def _op_clv(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.V_FLAG, False)
        return 0

    def _op_cld(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.D_FLAG, False)
        return 0

    def _op_sed(self, addr: int, crossed_page: bool) -> int:
        self._set_flag(self.D_FLAG, True)
        return 0

    # ── No operation ───────────────────────────────────────────────

    def _op_nop(self, addr: int, crossed_page: bool) -> int:
        return 0

    # ═══════════════════════════════════════════════════════════════
    #  Interrupt handling
    # ═══════════════════════════════════════════════════════════════

    def reset(self) -> None:
        """Reset the CPU: load reset vector from $FFFC-$FFFD."""
        self.pc = self._read_word(0xFFFC)
        self.sp = 0xFD
        self.status = 0x24  # I + unused flags set
        self.a = self.x = self.y = 0
        self.cycles = 0
        self._interrupt_type = 0

    def nmi(self) -> None:
        """Non-Maskable Interrupt — set pending flag for next step()."""
        self._interrupt_type = 1

    def irq(self) -> None:
        """Interrupt Request — set pending flag (ignored if I flag is set)."""
        self._interrupt_type = 2

    def _handle_interrupt(self, nmi: bool = False) -> int:
        """Handle a pending hardware interrupt. Returns cycles consumed."""
        # NMI always fires; IRQ only if I flag is clear
        if nmi or not self._get_flag(self.I_FLAG):
            self._push_word(self.pc)
            # Push status with B=0 for hardware interrupts (B=1 only for BRK)
            self._push(self.status & ~(1 << self.B_FLAG))
            self._set_flag(self.I_FLAG, True)
            if nmi:
                self.pc = self._read_word(0xFFFA)
            else:
                self.pc = self._read_word(0xFFFE)
            self._interrupt_type = 0
            return 7
        self._interrupt_type = 0
        return 0

    # ═══════════════════════════════════════════════════════════════
    #  Main step method
    # ═══════════════════════════════════════════════════════════════

    def step(self) -> int:
        """Execute one instruction. Returns the number of CPU cycles consumed."""
        # 1. Check for pending interrupts
        if self._interrupt_type == 1:  # NMI
            return self._handle_interrupt(nmi=True)
        if self._interrupt_type == 2:  # IRQ
            if not self._get_flag(self.I_FLAG):
                return self._handle_interrupt(nmi=False)
            # IRQ blocked by I flag — clear pending and consume no cycles
            self._interrupt_type = 0
            return 0

        # 2. Fetch opcode
        opcode = self._read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF

        # 3. Look up instruction table (list index — O(1) no hashing)
        instr = self._opcode_table[opcode]

        # 4. Resolve operand address via addressing mode
        addr, crossed_page = instr.addressing_mode_fn()

        # 5. Execute the instruction
        extra_cycles = instr.operation_fn(addr, crossed_page)

        # 6. Update total cycles
        total = instr.base_cycles + extra_cycles
        self.cycles += total
        return total

    # ═══════════════════════════════════════════════════════════════
    #  Opcode table builder
    # ═══════════════════════════════════════════════════════════════

    def _build_opcode_table(self) -> list[Instruction]:
        """Build the 256-entry opcode → Instruction array.

        All 256 slots are filled: undefined opcodes map to a NOP
        fallback so that ``step()`` can use direct list indexing
        instead of slower dict-hash lookups.
        """
        nop = Instruction("NOP", self._addr_imp, self._op_nop, 2)
        t: list[Instruction] = [nop] * 256

        def add(
            opcodes: list[int],
            mnemonic: str,
            addr_fn: Callable[..., tuple[int, bool]],
            op_fn: Callable[..., int],
            base_cycles: int,
        ) -> None:
            instr = Instruction(mnemonic, addr_fn, op_fn, base_cycles)
            for op in opcodes:
                t[op] = instr

        # ── LDA (8 opcodes) ────────────────────────────────────────
        add([0xA9], "LDA", self._addr_imm, self._op_lda, 2)
        add([0xA5], "LDA", self._addr_zp, self._op_lda, 3)
        add([0xB5], "LDA", self._addr_zpx, self._op_lda, 4)
        add([0xAD], "LDA", self._addr_abs, self._op_lda, 4)
        add([0xBD], "LDA", self._addr_absx, self._op_lda, 4)
        add([0xB9], "LDA", self._addr_absy, self._op_lda, 4)
        add([0xA1], "LDA", self._addr_izx, self._op_lda, 6)
        add([0xB1], "LDA", self._addr_izy, self._op_lda, 5)

        # ── LDX (5 opcodes) ────────────────────────────────────────
        add([0xA2], "LDX", self._addr_imm, self._op_ldx, 2)
        add([0xA6], "LDX", self._addr_zp, self._op_ldx, 3)
        add([0xB6], "LDX", self._addr_zpy, self._op_ldx, 4)
        add([0xAE], "LDX", self._addr_abs, self._op_ldx, 4)
        add([0xBE], "LDX", self._addr_absy, self._op_ldx, 4)

        # ── LDY (5 opcodes) ────────────────────────────────────────
        add([0xA0], "LDY", self._addr_imm, self._op_ldy, 2)
        add([0xA4], "LDY", self._addr_zp, self._op_ldy, 3)
        add([0xB4], "LDY", self._addr_zpx, self._op_ldy, 4)
        add([0xAC], "LDY", self._addr_abs, self._op_ldy, 4)
        add([0xBC], "LDY", self._addr_absx, self._op_ldy, 4)

        # ── STA (7 opcodes) ────────────────────────────────────────
        add([0x85], "STA", self._addr_zp, self._op_sta, 3)
        add([0x95], "STA", self._addr_zpx, self._op_sta, 4)
        add([0x8D], "STA", self._addr_abs, self._op_sta, 4)
        add([0x9D], "STA", self._addr_absx, self._op_sta, 5)
        add([0x99], "STA", self._addr_absy, self._op_sta, 5)
        add([0x81], "STA", self._addr_izx, self._op_sta, 6)
        add([0x91], "STA", self._addr_izy, self._op_sta, 6)

        # ── STX (3 opcodes) ────────────────────────────────────────
        add([0x86], "STX", self._addr_zp, self._op_stx, 3)
        add([0x96], "STX", self._addr_zpy, self._op_stx, 4)
        add([0x8E], "STX", self._addr_abs, self._op_stx, 4)

        # ── STY (3 opcodes) ────────────────────────────────────────
        add([0x84], "STY", self._addr_zp, self._op_sty, 3)
        add([0x94], "STY", self._addr_zpx, self._op_sty, 4)
        add([0x8C], "STY", self._addr_abs, self._op_sty, 4)

        # ── ADC (8 opcodes) ────────────────────────────────────────
        add([0x69], "ADC", self._addr_imm, self._op_adc, 2)
        add([0x65], "ADC", self._addr_zp, self._op_adc, 3)
        add([0x75], "ADC", self._addr_zpx, self._op_adc, 4)
        add([0x6D], "ADC", self._addr_abs, self._op_adc, 4)
        add([0x7D], "ADC", self._addr_absx, self._op_adc, 4)
        add([0x79], "ADC", self._addr_absy, self._op_adc, 4)
        add([0x61], "ADC", self._addr_izx, self._op_adc, 6)
        add([0x71], "ADC", self._addr_izy, self._op_adc, 5)

        # ── SBC (8 opcodes) ────────────────────────────────────────
        add([0xE9], "SBC", self._addr_imm, self._op_sbc, 2)
        add([0xE5], "SBC", self._addr_zp, self._op_sbc, 3)
        add([0xF5], "SBC", self._addr_zpx, self._op_sbc, 4)
        add([0xED], "SBC", self._addr_abs, self._op_sbc, 4)
        add([0xFD], "SBC", self._addr_absx, self._op_sbc, 4)
        add([0xF9], "SBC", self._addr_absy, self._op_sbc, 4)
        add([0xE1], "SBC", self._addr_izx, self._op_sbc, 6)
        add([0xF1], "SBC", self._addr_izy, self._op_sbc, 5)

        # ── INC (4 opcodes) ────────────────────────────────────────
        add([0xE6], "INC", self._addr_zp, self._op_inc, 5)
        add([0xF6], "INC", self._addr_zpx, self._op_inc, 6)
        add([0xEE], "INC", self._addr_abs, self._op_inc, 6)
        add([0xFE], "INC", self._addr_absx, self._op_inc, 7)

        # ── INX (1 opcode) ─────────────────────────────────────────
        add([0xE8], "INX", self._addr_imp, self._op_inx, 2)

        # ── INY (1 opcode) ─────────────────────────────────────────
        add([0xC8], "INY", self._addr_imp, self._op_iny, 2)

        # ── DEC (4 opcodes) ────────────────────────────────────────
        add([0xC6], "DEC", self._addr_zp, self._op_dec, 5)
        add([0xD6], "DEC", self._addr_zpx, self._op_dec, 6)
        add([0xCE], "DEC", self._addr_abs, self._op_dec, 6)
        add([0xDE], "DEC", self._addr_absx, self._op_dec, 7)

        # ── DEX (1 opcode) ─────────────────────────────────────────
        add([0xCA], "DEX", self._addr_imp, self._op_dex, 2)

        # ── DEY (1 opcode) ─────────────────────────────────────────
        add([0x88], "DEY", self._addr_imp, self._op_dey, 2)

        # ── AND (8 opcodes) ────────────────────────────────────────
        add([0x29], "AND", self._addr_imm, self._op_and, 2)
        add([0x25], "AND", self._addr_zp, self._op_and, 3)
        add([0x35], "AND", self._addr_zpx, self._op_and, 4)
        add([0x2D], "AND", self._addr_abs, self._op_and, 4)
        add([0x3D], "AND", self._addr_absx, self._op_and, 4)
        add([0x39], "AND", self._addr_absy, self._op_and, 4)
        add([0x21], "AND", self._addr_izx, self._op_and, 6)
        add([0x31], "AND", self._addr_izy, self._op_and, 5)

        # ── ORA (8 opcodes) ────────────────────────────────────────
        add([0x09], "ORA", self._addr_imm, self._op_ora, 2)
        add([0x05], "ORA", self._addr_zp, self._op_ora, 3)
        add([0x15], "ORA", self._addr_zpx, self._op_ora, 4)
        add([0x0D], "ORA", self._addr_abs, self._op_ora, 4)
        add([0x1D], "ORA", self._addr_absx, self._op_ora, 4)
        add([0x19], "ORA", self._addr_absy, self._op_ora, 4)
        add([0x01], "ORA", self._addr_izx, self._op_ora, 6)
        add([0x11], "ORA", self._addr_izy, self._op_ora, 5)

        # ── EOR (8 opcodes) ────────────────────────────────────────
        add([0x49], "EOR", self._addr_imm, self._op_eor, 2)
        add([0x45], "EOR", self._addr_zp, self._op_eor, 3)
        add([0x55], "EOR", self._addr_zpx, self._op_eor, 4)
        add([0x4D], "EOR", self._addr_abs, self._op_eor, 4)
        add([0x5D], "EOR", self._addr_absx, self._op_eor, 4)
        add([0x59], "EOR", self._addr_absy, self._op_eor, 4)
        add([0x41], "EOR", self._addr_izx, self._op_eor, 6)
        add([0x51], "EOR", self._addr_izy, self._op_eor, 5)

        # ── BIT (2 opcodes) ────────────────────────────────────────
        add([0x24], "BIT", self._addr_zp, self._op_bit, 3)
        add([0x2C], "BIT", self._addr_abs, self._op_bit, 4)

        # ── ASL (5 opcodes) ────────────────────────────────────────
        add([0x0A], "ASL", self._addr_acc, self._op_asl_acc, 2)
        add([0x06], "ASL", self._addr_zp, self._op_asl, 5)
        add([0x16], "ASL", self._addr_zpx, self._op_asl, 6)
        add([0x0E], "ASL", self._addr_abs, self._op_asl, 6)
        add([0x1E], "ASL", self._addr_absx, self._op_asl, 7)

        # ── LSR (5 opcodes) ────────────────────────────────────────
        add([0x4A], "LSR", self._addr_acc, self._op_lsr_acc, 2)
        add([0x46], "LSR", self._addr_zp, self._op_lsr, 5)
        add([0x56], "LSR", self._addr_zpx, self._op_lsr, 6)
        add([0x4E], "LSR", self._addr_abs, self._op_lsr, 6)
        add([0x5E], "LSR", self._addr_absx, self._op_lsr, 7)

        # ── ROL (5 opcodes) ────────────────────────────────────────
        add([0x2A], "ROL", self._addr_acc, self._op_rol_acc, 2)
        add([0x26], "ROL", self._addr_zp, self._op_rol, 5)
        add([0x36], "ROL", self._addr_zpx, self._op_rol, 6)
        add([0x2E], "ROL", self._addr_abs, self._op_rol, 6)
        add([0x3E], "ROL", self._addr_absx, self._op_rol, 7)

        # ── ROR (5 opcodes) ────────────────────────────────────────
        add([0x6A], "ROR", self._addr_acc, self._op_ror_acc, 2)
        add([0x66], "ROR", self._addr_zp, self._op_ror, 5)
        add([0x76], "ROR", self._addr_zpx, self._op_ror, 6)
        add([0x6E], "ROR", self._addr_abs, self._op_ror, 6)
        add([0x7E], "ROR", self._addr_absx, self._op_ror, 7)

        # ── CMP (8 opcodes) ────────────────────────────────────────
        add([0xC9], "CMP", self._addr_imm, self._op_cmp, 2)
        add([0xC5], "CMP", self._addr_zp, self._op_cmp, 3)
        add([0xD5], "CMP", self._addr_zpx, self._op_cmp, 4)
        add([0xCD], "CMP", self._addr_abs, self._op_cmp, 4)
        add([0xDD], "CMP", self._addr_absx, self._op_cmp, 4)
        add([0xD9], "CMP", self._addr_absy, self._op_cmp, 4)
        add([0xC1], "CMP", self._addr_izx, self._op_cmp, 6)
        add([0xD1], "CMP", self._addr_izy, self._op_cmp, 5)

        # ── CPX (3 opcodes) ────────────────────────────────────────
        add([0xE0], "CPX", self._addr_imm, self._op_cpx, 2)
        add([0xE4], "CPX", self._addr_zp, self._op_cpx, 3)
        add([0xEC], "CPX", self._addr_abs, self._op_cpx, 4)

        # ── CPY (3 opcodes) ────────────────────────────────────────
        add([0xC0], "CPY", self._addr_imm, self._op_cpy, 2)
        add([0xC4], "CPY", self._addr_zp, self._op_cpy, 3)
        add([0xCC], "CPY", self._addr_abs, self._op_cpy, 4)

        # ── Branch instructions (8 opcodes) ────────────────────────
        add([0x90], "BCC", self._addr_rel, self._op_bcc, 2)
        add([0xB0], "BCS", self._addr_rel, self._op_bcs, 2)
        add([0xF0], "BEQ", self._addr_rel, self._op_beq, 2)
        add([0xD0], "BNE", self._addr_rel, self._op_bne, 2)
        add([0x30], "BMI", self._addr_rel, self._op_bmi, 2)
        add([0x10], "BPL", self._addr_rel, self._op_bpl, 2)
        add([0x50], "BVC", self._addr_rel, self._op_bvc, 2)
        add([0x70], "BVS", self._addr_rel, self._op_bvs, 2)

        # ── JMP (2 opcodes) ────────────────────────────────────────
        add([0x4C], "JMP", self._addr_abs, self._op_jmp, 3)
        add([0x6C], "JMP", self._addr_ind, self._op_jmp, 5)

        # ── JSR / RTS / RTI / BRK ──────────────────────────────────
        add([0x20], "JSR", self._addr_abs, self._op_jsr, 6)
        add([0x60], "RTS", self._addr_imp, self._op_rts, 6)
        add([0x40], "RTI", self._addr_imp, self._op_rti, 6)
        add([0x00], "BRK", self._addr_imp, self._op_brk, 7)

        # ── Stack instructions ─────────────────────────────────────
        add([0x48], "PHA", self._addr_imp, self._op_pha, 3)
        add([0x68], "PLA", self._addr_imp, self._op_pla, 4)
        add([0x08], "PHP", self._addr_imp, self._op_php, 3)
        add([0x28], "PLP", self._addr_imp, self._op_plp, 4)
        add([0x9A], "TXS", self._addr_imp, self._op_txs, 2)
        add([0xBA], "TSX", self._addr_imp, self._op_tsx, 2)

        # ── Register transfers ─────────────────────────────────────
        add([0xAA], "TAX", self._addr_imp, self._op_tax, 2)
        add([0x8A], "TXA", self._addr_imp, self._op_txa, 2)
        add([0xA8], "TAY", self._addr_imp, self._op_tay, 2)
        add([0x98], "TYA", self._addr_imp, self._op_tya, 2)
        add([0x9B], "TXY", self._addr_imp, self._op_txy, 2)

        # ── Flag instructions ──────────────────────────────────────
        add([0x18], "CLC", self._addr_imp, self._op_clc, 2)
        add([0x38], "SEC", self._addr_imp, self._op_sec, 2)
        add([0x58], "CLI", self._addr_imp, self._op_cli, 2)
        add([0x78], "SEI", self._addr_imp, self._op_sei, 2)
        add([0xB8], "CLV", self._addr_imp, self._op_clv, 2)
        add([0xD8], "CLD", self._addr_imp, self._op_cld, 2)
        add([0xF8], "SED", self._addr_imp, self._op_sed, 2)

        # ── NOP ────────────────────────────────────────────────────
        add([0xEA], "NOP", self._addr_imp, self._op_nop, 2)

        return t
