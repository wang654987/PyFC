# M2: 完整 CPU 指令集

> 目标：实现完整的 MOS 6502 指令集
> 验收标准：通过 nestest.nes 测试 ROM（官方 6502 指令测试）

---

## 任务清单

### 2.1 所有寻址模式实现

**目标**：实现 6502 的所有寻址模式

- [ ] 立即寻址（Immediate）- `LDA #$10`
- [ ] 零页寻址（Zero Page）- `LDA $10`
- [ ] 零页X寻址（Zero Page,X）- `LDA $10,X`
- [ ] 零页Y寻址（Zero Page,Y）- `LDA $10,Y`
- [ ] 绝对寻址（Absolute）- `LDA $1234`
- [ ] 绝对X寻址（Absolute,X）- `LDA $1234,X`
- [ ] 绝对Y寻址（Absolute,Y）- `LDA $1234,Y`
- [ ] X间接寻址（Indirect,X）- `LDA ($10,X)`
- [ ] Y间接寻址（Indirect,Y）- `LDA ($10),Y`
- [ ] 相对寻址（Relative）- `BEQ label`
- [ ] 隐含寻址（Implicit）- `NOP`
- [ ] 累加器寻址（Accumulator）- `LSR A`
- [ ] 间接寻址（Indirect）- `JMP ($1234)`

**实现框架**：
```python
def _get_address(self, mode: str) -> tuple[int, int]:
    """根据寻址模式获取操作地址和额外周期"""
    match mode:
        case "IMM":
            addr = self.pc
            self.pc += 1
            return addr, 0
        case "ZP":
            addr = self._read(self.pc)
            self.pc += 1
            return addr, 0
        case "ZPX":
            addr = (self._read(self.pc) + self.x) & 0xFF
            self.pc += 1
            return addr, 0
        # ... 更多寻址模式
```

**VideCoding 检查点**：
```python
# 测试各寻址模式
# Zero Page
bus.write(0x0010, 0x42)
cpu.pc = 0x0000
bus.write(0x0000, 0xA5)  # LDA $10
bus.write(0x0001, 0x10)
cpu.step()
assert cpu.a == 0x42
```

---

### 2.2 算术/逻辑指令

**目标**：实现所有算术和逻辑运算指令

**算术指令**：
- [ ] ADC（加法）- 0x69, 0x65, 0x75, 0x6D, 0x7D, 0x79, 0x61, 0x71
- [ ] SBC（减法）- 0xE9, 0xE5, 0xF5, 0xED, 0xFD, 0xF9, 0xE1, 0xF1
- [ ] INC（内存递增）- 0xE6, 0xF6, 0xEE, 0xFE
- [ ] INX（X递增）- 0xE8
- [ ] INY（Y递增）- 0xC8
- [ ] DEC（内存递减）- 0xC6, 0xD6, 0xCE, 0xDE
- [ ] DEX（X递减）- 0xCA
- [ ] DEY（Y递减）- 0x88

**逻辑指令**：
- [ ] AND（逻辑与）- 0x29, 0x25, 0x35, 0x2D, 0x3D, 0x39, 0x21, 0x31
- [ ] ORA（逻辑或）- 0x09, 0x05, 0x15, 0x0D, 0x1D, 0x19, 0x01, 0x11
- [ ] EOR（逻辑异或）- 0x49, 0x45, 0x55, 0x4D, 0x5D, 0x59, 0x41, 0x51
- [ ] BIT（位测试）- 0x24, 0x2C

**移位指令**：
- [ ] ASL（算术左移）- 0x0A, 0x06, 0x16, 0x0E, 0x1E
- [ ] LSR（逻辑右移）- 0x4A, 0x46, 0x56, 0x4E, 0x5E
- [ ] ROL（循环左移）- 0x2A, 0x26, 0x36, 0x2E, 0x3E
- [ ] ROR（循环右移）- 0x6A, 0x66, 0x76, 0x6E, 0x7E

**ADC 实现示例**：
```python
def _adc(self, value: int):
    carry = self._get_flag('C')
    result = self.a + value + carry
    
    # 设置标志位
    self._set_flag('C', result > 0xFF)
    self._set_flag('Z', (result & 0xFF) == 0)
    self._set_flag('V', (~(self.a ^ value) & (self.a ^ result) & 0x80))
    self._set_flag('N', result & 0x80)
    
    self.a = result & 0xFF
```

**VideCoding 检查点**：
```python
# ADC 测试
cpu.a = 0x50
cpu._adc(0x30)
assert cpu.a == 0x80
assert cpu._get_flag('V') == 1  # 溢出
```

---

### 2.3 比较/分支指令

**目标**：实现比较和条件分支指令

**比较指令**：
- [ ] CMP（比较累加器）- 0xC9, 0xC5, 0xD5, 0xCD, 0xDD, 0xD9, 0xC1, 0xD1
- [ ] CPX（比较X）- 0xE0, 0xE4, 0xEC
- [ ] CPY（比较Y）- 0xC0, 0xC4, 0xCC

**分支指令**：
- [ ] BCC（进位清除分支）- 0x90
- [ ] BCS（进位设置分支）- 0xB0
- [ ] BEQ（零标志分支）- 0xF0
- [ ] BNE（零标志清除分支）- 0xD0
- [ ] BMI（负数分支）- 0x30
- [ ] BPL（正数分支）- 0x10
- [ ] BVC（溢出清除分支）- 0x50
- [ ] BVS（溢出设置分支）- 0x70

**CMP 实现示例**：
```python
def _cmp(self, register: int, value: int):
    result = register - value
    self._set_flag('C', register >= value)
    self._set_flag('Z', register == value)
    self._set_flag('N', result & 0x80)
```

**分支实现示例**：
```python
def _branch(self, condition: bool):
    offset = self._read(self.pc)
    self.pc += 1
    
    if offset & 0x80:  # 负数
        offset -= 256
    
    if condition:
        old_pc = self.pc
        self.pc += offset
        self.cycles += 1  # 额外周期
        if (old_pc & 0xFF00) != (self.pc & 0xFF00):
            self.cycles += 1  # 跨页额外周期
```

**VideCoding 检查点**：
```python
# BEQ 测试
cpu._set_flag('Z', True)
bus.write(0x0000, 0xF0)  # BEQ +5
bus.write(0x0001, 0x05)
cpu.pc = 0x0000
cpu.step()
assert cpu.pc == 0x0007  # 2 + 5
```

---

### 2.4 栈操作指令

**目标**：实现栈相关指令

- [ ] PHA（压入累加器）- 0x48
- [ ] PLA（弹出到累加器）- 0x68
- [ ] PHP（压入状态寄存器）- 0x08
- [ ] PLP（弹出到状态寄存器）- 0x28
- [ ] TXS（X传到栈指针）- 0x9A
- [ ] TSX（栈指针传到X）- 0xBA

**栈操作实现**：
```python
def _push(self, value: int):
    self._write(0x0100 + self.sp, value)
    self.sp = (self.sp - 1) & 0xFF

def _pull(self) -> int:
    self.sp = (self.sp + 1) & 0xFF
    return self._read(0x0100 + self.sp)
```

**VideCoding 检查点**：
```python
# PHA/PLA 测试
cpu.a = 0x42
cpu._push(cpu.a)
cpu.a = 0x00
cpu.a = cpu._pull()
assert cpu.a == 0x42
```

---

### 2.5 跳转/子程序指令

**目标**：实现跳转和子程序调用指令

- [ ] JMP 绝对（0x4C）
- [ ] JMP 间接（0x6C）
- [ ] JSR（跳转到子程序）- 0x20
- [ ] RTS（从子程序返回）- 0x60
- [ ] RTI（从中断返回）- 0x40
- [ ] BRK（中断指令）- 0x00

**JSR/RTS 实现**：
```python
def _jsr(self):
    addr = self._read(self.pc) | (self._read(self.pc + 1) << 8)
    self.pc += 2
    
    # 压入返回地址（PC-1）
    self._push((self.pc - 1) >> 8)
    self._push((self.pc - 1) & 0xFF)
    
    self.pc = addr
    self.cycles += 6

def _rts(self):
    low = self._pull()
    high = self._pull()
    self.pc = ((high << 8) | low) + 1
    self.cycles += 6
```

**VideCoding 检查点**：
```python
# JSR/RTS 测试
bus.write(0x0000, 0x20)  # JSR $1000
bus.write(0x0001, 0x00)
bus.write(0x0002, 0x10)
bus.write(0x1000, 0x60)  # RTS

cpu.pc = 0x0000
cpu.step()  # JSR
assert cpu.pc == 0x1000
cpu.step()  # RTS
assert cpu.pc == 0x0003
```

---

### 2.6 中断处理

**目标**：实现完整的中断机制

- [ ] NMI（不可屏蔽中断）处理
- [ ] IRQ（中断请求）处理
- [ ] Reset 中断处理
- [ ] 中断向量读取（$FFFA-$FFFF）

**中断向量表**：
```
$FFFA-$FFFB: NMI 向量
$FFFC-$FFFD: Reset 向量
$FFFE-$FFFF: IRQ/BRK 向量
```

**NMI 实现**：
```python
def nmi(self):
    self._push(self.pc >> 8)
    self._push(self.pc & 0xFF)
    self._push(self.status)
    
    self._set_flag('I', True)
    self.pc = self._read(0xFFFA) | (self._read(0xFFFB) << 8)
    self.cycles += 7
```

**VideCoding 检查点**：
```python
# NMI 测试
bus.write(0xFFFA, 0x00)  # NMI 向量低字节
bus.write(0xFFFB, 0x80)  # NMI 向量高字节
cpu.pc = 0x0000
cpu.nmi()
assert cpu.pc == 0x8000
```

---

### 2.7 测试验证

**目标**：使用 nestest.nes 验证 CPU 实现

- [ ] 下载 nestest.nes 测试 ROM
- [ ] 实现测试模式（自动运行）
- [ ] 解析测试输出
- [ ] 修复失败的测试用例
- [ ] 通过所有官方指令测试

**测试运行方式**：
```python
# 加载 nestest.nes
cart = Cartridge("nestest.nes")
bus = Bus()
bus.cartridge = cart

# 设置测试模式
cpu = CPU6502(bus)
cpu.pc = 0xC000  # nestest 自动模式入口

# 运行测试
while True:
    cpu.step()
    # 检查测试结果
```

**VideCoding 检查点**：
```
运行 nestest.nes 后输出：
- 所有测试通过（00 00 在 $02 和 $03）
- 无错误代码
```

---

## M2 完成标准

- [ ] 实现所有 151 条官方指令
- [ ] 实现所有 13 种寻址模式
- [ ] 正确处理所有标志位
- [ ] 正确处理中断
- [ ] 通过 nestest.nes 测试
