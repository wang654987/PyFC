# Vibecoding Prompt 02: CPU 6502 完整实现

## 概述

实现完整的 MOS 6502 CPU 模拟器。这是整个模拟器的核心模块，需要实现所有 56 条官方指令（151 个操作码）、13 种寻址模式、以及完整的中断机制。

## 前置条件

- `src/cartridge.py` 和 `src/palette.py` 已实现（但你的 CPU 测试不需要它们）
- CPU 只依赖一个 `Bus` 接口（有 `read(addr)` 和 `write(addr, val)` 方法）
- 测试时使用 **MemoryStub**（一个简单的 dict 包装类），不依赖真实的 Bus

## 你要创建/修改的文件

### `src/cpu.py` — 6502 CPU 模拟器（核心文件，约 800-1200 行）

#### 1. 寄存器定义

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bus import Bus

class CPU6502:
    """MOS 6502 CPU 模拟器。"""

    # ---- 寄存器 ----
    a: int       # 累加器 (0-255)
    x: int       # X 索引寄存器 (0-255)
    y: int       # Y 索引寄存器 (0-255)
    sp: int      # 栈指针 (0-255)，实际地址 = 0x0100 + sp
    pc: int      # 程序计数器 (0-65535)
    status: int  # 状态寄存器 (0-255)
    cycles: int  # 已消耗总周期数

    # ---- 标志位常量 ----
    C_FLAG: int = 0  # Carry（进位）
    Z_FLAG: int = 1  # Zero（零）
    I_FLAG: int = 2  # Interrupt Disable（中断禁止）
    D_FLAG: int = 3  # Decimal（十进制模式，NES 不使用）
    B_FLAG: int = 4  # Break（BRK 指令标志）
    U_FLAG: int = 5  # Unused（未使用，通常为 1）
    V_FLAG: int = 6  # Overflow（溢出）
    N_FLAG: int = 7  # Negative（负数）
```

#### 2. 初始化与基础方法

```python
def __init__(self, bus: Bus) -> None:
    self.bus = bus
    self.a = 0
    self.x = 0
    self.y = 0
    self.sp = 0xFD
    self.pc = 0x0000
    self.status = 0x24  # I flag + unused flag set
    self.cycles = 0
    self._interrupt_type: int = 0  # 0=none, 1=NMI, 2=IRQ

def _read(self, address: int) -> int:
    """通过总线读取一个字节。"""
    return self.bus.read(address & 0xFFFF)

def _write(self, address: int, value: int) -> None:
    """通过总线写入一个字节。"""
    self.bus.write(address & 0xFFFF, value & 0xFF)

def _read_word(self, address: int) -> int:
    """读取 16 位小端字。"""
    lo = self._read(address)
    hi = self._read((address + 1) & 0xFFFF)
    return lo | (hi << 8)

def _get_flag(self, flag: int) -> int:
    """获取标志位值（0 或 1）。"""
    return (self.status >> flag) & 1

def _set_flag(self, flag: int, value: bool | int) -> None:
    """设置标志位。"""
    if value:
        self.status |= (1 << flag)
    else:
        self.status &= ~(1 << flag)
```

#### 3. 栈操作

```python
def _push(self, value: int) -> None:
    """压栈：写入 0x0100+sp，sp 减 1。"""
    self._write(0x0100 | self.sp, value & 0xFF)
    self.sp = (self.sp - 1) & 0xFF

def _pull(self) -> int:
    """出栈：sp 加 1，读取 0x0100+sp。"""
    self.sp = (self.sp + 1) & 0xFF
    return self._read(0x0100 | self.sp)

def _push_word(self, value: int) -> None:
    """压入 16 位值（高字节先入栈）。"""
    self._push((value >> 8) & 0xFF)
    self._push(value & 0xFF)
```

#### 4. 指令表设计（两层查找表）

使用 **函数表 + opcode 字典** 的设计：

```python
from dataclasses import dataclass
from collections.abc import Callable

@dataclass
class Instruction:
    """指令描述符。"""
    mnemonic: str                          # 助记符，如 "LDA"
    addressing_mode: str                   # 寻址模式，如 "IMM", "ZP", "ABS"
    operation: Callable[..., int]          # 指令执行函数
    base_cycles: int                       # 基础周期数

# 类变量：OPCODE_TABLE: dict[int, Instruction]
# 在类初始化时构建，映射 opcode → Instruction
```

**指令执行函数签名**：`def _op_xxx(self, addr: int, crossed_page: bool) -> int`

- `addr`: 操作数地址（寻址模式函数计算得出）
- `crossed_page`: 是否发生了跨页
- 返回值：需要额外增加的周期数（通常跨页时返回 +1）

**寻址模式函数签名**：`def _addr_xxx(self) -> tuple[int, bool]`

- 返回 `(操作数地址, 是否跨页)`

#### 5. 所有寻址模式（13 种）

| 寻址模式 | 函数名 | 说明 | 周期 |
|---------|--------|------|------|
| Implicit | `_addr_imp` | 无操作数（NOP, RTS 等） | +0 |
| Accumulator | `_addr_acc` | 操作累加器（ASL A 等） | +0 |
| Immediate | `_addr_imm` | 操作数在 PC 后一字节 | +0 |
| Zero Page | `_addr_zp` | 零页（$00-$FF） | +0 |
| Zero Page,X | `_addr_zpx` | 零页 + X（会绕回） | +0 |
| Zero Page,Y | `_addr_zpy` | 零页 + Y（会绕回） | +0 |
| Absolute | `_addr_abs` | 16位绝对地址 | +0 |
| Absolute,X | `_addr_absx` | 绝对地址 + X | 跨页+1 |
| Absolute,Y | `_addr_absy` | 绝对地址 + Y | 跨页+1 |
| Indirect | `_addr_ind` | 间接跳转 JMP ($xxxx) | +0 |
| (Indirect,X) | `_addr_izx` | X 间接寻址 | +0 |
| (Indirect),Y | `_addr_izy` | Y 间接寻址 | 跨页+1 |
| Relative | `_addr_rel` | 相对分支（-128 ~ +127） | 跨页+1-2 |

**重要实现注意**：
- JMP 间接寻址 (`_addr_ind`) 存在 6502 的页面边界 bug：`JMP ($xxFF)` 读取的第二个字节来自 `$xx00` 而非 `$xxFF+1`（6502 不会跨页读取）
- 零页寻址中的 X/Y 偏移会绕回（`(zp + X) & 0xFF`）

#### 6. 所有指令（56 条，151 个操作码）

**加载/存储指令**：
- `LDA` (0xA9,0xA5,0xB5,0xAD,0xBD,0xB9,0xA1,0xB1) — 加载到累加器
- `LDX` (0xA2,0xA6,0xB6,0xAE,0xBE) — 加载到 X
- `LDY` (0xA0,0xA4,0xB4,0xAC,0xBC) — 加载到 Y
- `STA` (0x85,0x95,0x8D,0x9D,0x99,0x81,0x91) — 存储累加器
- `STX` (0x86,0x96,0x8E) — 存储 X
- `STY` (0x84,0x94,0x8C) — 存储 Y

**算术指令**：
- `ADC` (0x69,0x65,0x75,0x6D,0x7D,0x79,0x61,0x71) — 带进位加法
- `SBC` (0xE9,0xE5,0xF5,0xED,0xFD,0xF9,0xE1,0xF1) — 带借位减法
- `INC` (0xE6,0xF6,0xEE,0xFE) — 内存递增
- `INX` (0xE8) — X 递增
- `INY` (0xC8) — Y 递增
- `DEC` (0xC6,0xD6,0xCE,0xDE) — 内存递减
- `DEX` (0xCA) — X 递减
- `DEY` (0x88) — Y 递减

**逻辑指令**：
- `AND` (0x29,0x25,0x35,0x2D,0x3D,0x39,0x21,0x31) — 逻辑与
- `ORA` (0x09,0x05,0x15,0x0D,0x1D,0x19,0x01,0x11) — 逻辑或
- `EOR` (0x49,0x45,0x55,0x4D,0x5D,0x59,0x41,0x51) — 逻辑异或
- `BIT` (0x24,0x2C) — 位测试

**移位指令**：
- `ASL` (0x0A,0x06,0x16,0x0E,0x1E) — 算术左移
- `LSR` (0x4A,0x46,0x56,0x4E,0x5E) — 逻辑右移
- `ROL` (0x2A,0x26,0x36,0x2E,0x3E) — 循环左移
- `ROR` (0x6A,0x66,0x76,0x6E,0x7E) — 循环右移

**比较指令**：
- `CMP` (0xC9,0xC5,0xD5,0xCD,0xDD,0xD9,0xC1,0xD1) — 比较累加器
- `CPX` (0xE0,0xE4,0xEC) — 比较 X
- `CPY` (0xC0,0xC4,0xCC) — 比较 Y

**分支指令**（8 条，基于标志位条件跳转）：
- `BCC` (0x90), `BCS` (0xB0), `BEQ` (0xF0), `BNE` (0xD0)
- `BMI` (0x30), `BPL` (0x10), `BVC` (0x50), `BVS` (0x70)

**跳转/子程序指令**：
- `JMP` (0x4C ABS, 0x6C IND) — 跳转
- `JSR` (0x20) — 跳转到子程序
- `RTS` (0x60) — 从子程序返回
- `RTI` (0x40) — 从中断返回
- `BRK` (0x00) — 软件中断

**栈指令**：
- `PHA` (0x48), `PLA` (0x68) — 累加器压栈/出栈
- `PHP` (0x08), `PLP` (0x28) — 状态寄存器压栈/出栈
- `TXS` (0x9A) — X 传到栈指针
- `TSX` (0xBA) — 栈指针传到 X

**寄存器传输指令**：
- `TAX` (0xAA), `TXA` (0x8A) — A ↔ X
- `TAY` (0xA8), `TYA` (0x98) — A ↔ Y
- `TXY` (0x9B) — X → Y（非官方但常用）

**标志位指令**：
- `CLC` (0x18), `SEC` (0x38) — 清除/设置进位
- `CLI` (0x58), `SEI` (0x78) — 清除/设置中断禁止
- `CLV` (0xB8) — 清除溢出
- `CLD` (0xD8), `SED` (0xF8) — 清除/设置十进制

**其他指令**：
- `NOP` (0xEA) — 无操作

#### 7. 关键指令实现细节

**ADC（带进位加法）**：
```python
def _op_adc(self, addr: int, crossed_page: bool) -> int:
    value = self._read(addr)
    carry = self._get_flag(self.C_FLAG)
    result = self.a + value + carry

    self._set_flag(self.C_FLAG, result > 0xFF)
    self._set_flag(self.Z_FLAG, (result & 0xFF) == 0)
    # V 标志：符号溢出 = ((A ^ result) & (value ^ result) & 0x80)
    self._set_flag(self.V_FLAG, (~(self.a ^ value) & (self.a ^ result)) & 0x80)
    self._set_flag(self.N_FLAG, result & 0x80)

    self.a = result & 0xFF
    return 1 if crossed_page else 0
```

**SBC（带借位减法）**：SBC = ADC(~value)，即对操作数取反后做 ADC。

**BIT（位测试）**：
```python
def _op_bit(self, addr: int, crossed_page: bool) -> int:
    value = self._read(addr)
    self._set_flag(self.Z_FLAG, (self.a & value) == 0)
    self._set_flag(self.N_FLAG, value & 0x80)
    self._set_flag(self.V_FLAG, value & 0x40)
    return 0
```

**分支指令**统一使用一个辅助方法：
```python
def _branch(self, condition: bool) -> int:
    offset = self._read(self.pc)
    self.pc += 1
    if offset & 0x80:
        offset -= 256  # 符号扩展

    if condition:
        old_pc = self.pc
        self.pc += offset
        cycles = 1
        if (old_pc & 0xFF00) != (self.pc & 0xFF00):
            cycles += 1  # 跨页额外周期
        return cycles
    return 0
```

#### 8. 中断处理

```python
def reset(self) -> None:
    """复位 CPU：读取 $FFFC-$FFFD 的复位向量。"""
    self.pc = self._read_word(0xFFFC)
    self.sp = 0xFD
    self.status = 0x24
    self.a = self.x = self.y = 0
    self.cycles = 0
    self._interrupt_type = 0

def nmi(self) -> None:
    """
    不可屏蔽中断（NMI）。
    保存 PC 和 status 到栈，跳转到 $FFFA-$FFFB 的中断向量。
    不通过 step() 处理，而是设置 pending 标志。
    """
    self._interrupt_type = 1  # NMI pending

def irq(self) -> None:
    """
    中断请求（IRQ）。
    如果 I 标志未设置，保存 PC 和 status 到栈，跳转到 $FFFE-$FFFF。
    """
    self._interrupt_type = 2  # IRQ pending

def _handle_interrupt(self, nmi: bool = False) -> int:
    """处理中断，返回消耗的周期数。"""
    if nmi or not self._get_flag(self.I_FLAG):
        self._push_word(self.pc)
        # BRK 和 NMI/IRQ 使用不同方式标记
        status_to_push = self.status | (0x00 if nmi or self._interrupt_type == 2 else 0x10)
        self._push(status_to_push)
        self._set_flag(self.I_FLAG, True)
        if nmi:
            self.pc = self._read_word(0xFFFA)
        else:
            self.pc = self._read_word(0xFFFE)
        self._interrupt_type = 0
        return 7  # 中断处理消耗 7 个周期
    self._interrupt_type = 0
    return 0
```

#### 9. step() 主方法

```python
def step(self) -> int:
    """
    执行一条指令。

    流程：
    1. 检查待处理的中断
    2. 从 PC 读取操作码
    3. 查找指令表
    4. 执行寻址模式获取操作数地址
    5. 执行指令
    6. 返回消耗的周期数
    """
    # 1. 中断检查
    if self._interrupt_type == 1:  # NMI
        return self._handle_interrupt(nmi=True)
    if self._interrupt_type == 2 and not self._get_flag(self.I_FLAG):  # IRQ
        return self._handle_interrupt(nmi=False)

    # 2. 取指
    opcode = self._read(self.pc)
    self.pc = (self.pc + 1) & 0xFFFF

    # 3. 查找指令表
    instr = self._opcode_table.get(opcode)
    if instr is None:
        # 未知操作码：当作 NOP 处理
        return 2

    # 4. 寻址
    addr, crossed_page = instr.addressing_mode_fn(self)

    # 5. 执行
    extra_cycles = instr.operation_fn(self, addr, crossed_page)

    # 6. 更新总周期
    total = instr.base_cycles + extra_cycles
    self.cycles += total
    return total
```

#### 10. 操作码表构建

在 `__init__` 中或类初始化时，构建 `_opcode_table: dict[int, Instruction]`：

```python
# 使用 _build_opcode_table() 方法构建 256 个条目的映射表
# 每个操作码对应一个 Instruction 对象
# 未使用的操作码留空（step() 中当 NOP 处理）
```

## 测试要求

### `tests/test_cpu.py`

创建一个 **MemoryStub** 类用于测试：

```python
class MemoryStub:
    """模拟内存的测试替身，用于 CPU 单元测试。"""
    def __init__(self):
        self.memory: dict[int, int] = {}
    def read(self, address: int) -> int:
        return self.memory.get(address & 0xFFFF, 0)
    def write(self, address: int, value: int) -> None:
        self.memory[address & 0xFFFF] = value & 0xFF
```

至少包含以下测试用例（按类别组织）：

**寻址模式测试**：
1. `test_immediate_addressing` — LDA #$42 → a=0x42
2. `test_zero_page_addressing` — LDA $10（预设 $10=0x42）→ a=0x42
3. `test_zero_page_x_addressing` — LDA $10,X（X=5, 预设 $15=0x42）
4. `test_zero_page_wraparound` — ZP+X 超过 0xFF 时绕回
5. `test_absolute_addressing` — LDA $1234
6. `test_absolute_x_cross_page` — ABS+X 跨页检测
7. `test_indirect_x_addressing` — ($10,X) 间接寻址
8. `test_indirect_y_addressing` — ($10),Y 间接寻址
9. `test_jmp_indirect_bug` — JMP ($xxFF) 的 6502 页面边界 bug
10. `test_relative_forward` — BEQ 向前跳转
11. `test_relative_backward` — BNE 向后跳转
12. `test_relative_cross_page` — 分支跨页额外周期

**算术指令测试**：
13. `test_adc_no_carry` — ADC 无进位
14. `test_adc_with_carry` — ADC 有进位
15. `test_adc_overflow` — ADC 溢出（正+正=负）
16. `test_sbc_no_borrow` — SBC 无借位
17. `test_sbc_with_borrow` — SBC 有借位
18. `test_inc_zero_page` — INC 零页
19. `test_inc_wraps_to_zero` — INC 0xFF → 0x00, 设置 Z 标志

**逻辑指令测试**：
20. `test_and_zero` — AND #$00
21. `test_ora_set_bits` — ORA #$0F
22. `test_eor_toggle` — EOR #$FF
23. `test_bit_zero_flag` — BIT 设置 Z 标志
24. `test_bit_nv_flags` — BIT 将 bit7→N, bit6→V

**移位指令测试**：
25. `test_asl_accumulator` — ASL A（左移，bit7→C）
26. `test_lsr_accumulator` — LSR A（右移，bit0→C）
27. `test_rol_through_carry` — ROL 带进位循环
28. `test_ror_through_carry` — ROR 带进位循环

**分支指令测试**：
29. `test_beq_when_zero` — Z=1 时 BEQ 跳转
30. `test_bne_when_not_zero` — Z=0 时 BNE 跳转
31. `test_bcc_bcs_carry` — BCC/BCS 基于进位

**栈操作测试**：
32. `test_push_pull` — PHA + PLA 循环
33. `test_jsr_rts` — JSR 跳转 + RTS 返回
34. `test_rti_restore` — RTI 恢复状态和 PC

**中断测试**：
35. `test_reset_vector` — reset() 从 $FFFC 读取 PC
36. `test_nmi_saves_context` — NMI 压栈后跳转到 NMI 向量
37. `test_irq_blocked_by_i_flag` — I=1 时 IRQ 被忽略
38. `test_brk_sets_b_flag` — BRK 指令设置 B 标志

**传输指令测试**：
39. `test_tax_transfer` — TAX: A→X, 设置标志位
40. `test_tsx_roundtrip` — TXS + TSX 保持值不变

## 质量检查

```bash
# 1. ruff 代码风格检查
ruff check src/cpu.py tests/test_cpu.py

# 2. mypy 类型检查
mypy src/cpu.py

# 3. pytest 单元测试（必须全部通过）
pytest tests/test_cpu.py -v

# 4. 确保覆盖所有 151 个官方操作码（可以写一个验证脚本）
```

## 与其他模块的接口

| 被依赖模块 | 使用方式 |
|-----------|---------|
| `bus.py` | 通过 CPU.read(addr)/CPU.write(addr, val) 间接使用 |
| `emulator.py` | 创建 CPU 实例，调用 step()/reset()/nmi()/irq() |

CPU 通过 `self.bus.read(addr)` 和 `self.bus.write(addr, val)` 与外界交互，不知道 RAM/PPU/Cartridge 的具体实现。

## 验收标准

- [ ] 实现所有 56 条官方 6502 指令（151 个操作码）
- [ ] 实现所有 13 种寻址模式
- [ ] 实现完整的中断机制（NMI, IRQ, Reset, BRK）
- [ ] 正确设置所有状态标志位（C, Z, I, D, B, V, N）
- [ ] JMP 间接寻址的页面边界 bug 正确处理
- [ ] 所有 pytest 测试通过（40+）
- [ ] mypy 类型检查无错误
- [ ] ruff 代码风格检查无错误
