# M1: ROM 加载 + CPU 骨架

> 目标：能加载 ROM，CPU 能执行 NOP、LDA 等基本指令
> 验收标准：能加载超级玛丽 ROM，CPU 能执行基本指令并输出调试信息

---

## 任务清单

### 1.1 项目基础结构搭建

**目标**：创建项目目录结构和基础配置文件

- [x] 创建 `src/` 目录
- [x] 创建 `src/__init__.py`
- [x] 创建 `pyproject.toml` 配置文件
- [x] 创建 `README.md`
- [x] 创建 `tests/` 目录（可选）

**文件清单**：
```
src/
├── __init__.py
├── main.py
├── emulator.py
├── cpu.py
├── ppu.py
├── bus.py
├── ppu_bus.py
├── cartridge.py
├── input.py
├── renderer.py
└── palette.py
```

**VideCoding 检查点**：
- 运行 `python -c "import src"` 无报错
- 项目结构完整

---

### 1.2 ROM 加载模块（cartridge.py）

**目标**：实现 iNES 格式 ROM 文件解析

- [x] 定义 Cartridge 类结构
- [x] 实现 iNES 头部解析（16 字节）
- [x] 验证魔数 "NES\x1A"
- [x] 读取 PRG-ROM 银行数
- [x] 读取 CHR-ROM 银行数
- [x] 解析 Mapper 编号（Flag 6 & 7）
- [x] 解析镜像方式（水平/垂直）
- [x] 跳过 Trainer（如有，512 字节）
- [x] 读取 PRG-ROM 数据
- [x] 读取 CHR-ROM 数据
- [x] 实现 cpu_read() - Mapper 0 PRG-ROM 读取
- [x] 实现 cpu_write() - Mapper 0 忽略写入
- [x] 实现 ppu_read() - CHR-ROM 读取
- [x] 实现 ppu_write() - Mapper 0 忽略写入

**代码模板**：
```python
class Cartridge:
    def __init__(self, rom_path: str):
        # 1. 打开文件
        # 2. 读取16字节头部
        # 3. 验证 "NES\x1A"
        # 4. 解析银行数、Mapper、镜像
        # 5. 跳过Trainer
        # 6. 读取PRG-ROM
        # 7. 读取CHR-ROM
        pass
```

**VideCoding 检查点**：
```python
# 测试代码
cart = Cartridge("Super Mario Bros. (E) (PRG0) [!].nes")
print(f"Mapper: {cart.mapper_id}")
print(f"PRG Banks: {cart.prg_banks}")
print(f"CHR Banks: {cart.chr_banks}")
print(f"Mirror: {cart.mirror_mode}")
assert cart.mapper_id == 0
assert cart.prg_banks == 2
assert cart.chr_banks == 1
```

---

### 1.3 CPU 模块骨架（cpu.py）

**目标**：实现 CPU 基础结构和寄存器管理

- [x] 定义 CPU6502 类
- [x] 定义寄存器属性（A, X, Y, SP, PC, P）
- [x] 定义标志位常量（C, Z, I, D, B, V, N）
- [x] 实现 reset() 方法
- [x] 实现 _read() 和 _write() 方法
- [x] 实现 _get_flag() 和 _set_flag() 方法
- [x] 实现 step() 方法骨架
- [x] 实现 nmi() 和 irq() 方法骨架

**寄存器初始化**：
```python
def reset(self):
    self.a = 0
    self.x = 0
    self.y = 0
    self.sp = 0xFD
    self.pc = self._read(0xFFFC) | (self._read(0xFFFD) << 8)
    self.status = 0x24  # I flag set
    self.cycles = 0
```

**VideCoding 检查点**：
```python
cpu = CPU6502(bus)
cpu.reset()
assert cpu.pc != 0  # 从ROM读取了入口地址
assert cpu.sp == 0xFD
assert cpu.status & 0x04  # I flag set
```

---

### 1.4 总线模块（bus.py）

**目标**：实现 CPU 地址空间映射

- [x] 定义 Bus 类
- [x] 初始化 2KB RAM（0x0000-0x07FF）
- [x] 实现地址解码逻辑
- [x] 实现 read() 方法
- [x] 实现 write() 方法
- [x] 连接 CPU、PPU、Cartridge、Controller 引用

**地址映射**：
```python
def read(self, address: int) -> int:
    if address < 0x2000:        # RAM + 镜像
        return self.ram[address & 0x07FF]
    elif address < 0x4000:      # PPU 寄存器（镜像）
        return self.ppu.cpu_read(address)
    elif address == 0x4016:     # 手柄1
        return self.controller.read()
    elif address >= 0x4020:     # 卡带
        return self.cartridge.cpu_read(address)
    return 0
```

**VideCoding 检查点**：
```python
bus = Bus()
bus.write(0x0000, 0x42)
assert bus.read(0x0000) == 0x42
assert bus.read(0x0800) == 0x42  # 镜像
```

---

### 1.5 基础指令实现

**目标**：实现最基本的 CPU 指令

- [x] 实现 NOP（0xEA）- 无操作
- [x] 实现 LDA 立即寻址（0xA9）- 加载累加器
- [x] 实现 LDX 立即寻址（0xA2）- 加载X寄存器
- [x] 实现 LDY 立即寻址（0xA0）- 加载Y寄存器
- [x] 实现 STA 绝对寻址（0x8D）- 存储累加器
- [x] 实现 STX 绝对寻址（0x8E）- 存储X寄存器
- [x] 实现 STY 绝对寻址（0x8C）- 存储Y寄存器
- [x] 实现 JMP 绝对寻址（0x4C）- 跳转
- [x] 实现基本操作码解码框架

**指令实现示例**：
```python
def step(self):
    opcode = self._read(self.pc)
    self.pc += 1
    
    match opcode:
        case 0xEA:  # NOP
            self.cycles += 2
        case 0xA9:  # LDA Immediate
            self.a = self._read(self.pc)
            self.pc += 1
            self._set_flag('Z', self.a == 0)
            self._set_flag('N', self.a & 0x80)
            self.cycles += 2
        # ... 更多指令
```

**VideCoding 检查点**：
```python
# 写入测试程序到RAM
bus.write(0x0000, 0xA9)  # LDA #$42
bus.write(0x0001, 0x42)
bus.write(0x0002, 0xEA)  # NOP

cpu = CPU6502(bus)
cpu.pc = 0x0000
cpu.step()
assert cpu.a == 0x42
assert cpu.cycles == 2
```

---

## M1 完成标准

- [x] 能加载超级玛丽 ROM 文件
- [x] 能正确解析 iNES 头部信息
- [x] CPU 能执行基本指令
- [x] 总线能正确路由地址访问
- [x] 无语法错误，可导入运行
