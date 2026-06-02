# FC 模拟器设计文档

> 项目名称：PyFC（Python FC Emulator）
> 基于需求文档：requirements.md v1.0
> 设计风格：自然语言 + 伪代码
> 文档版本：v1.0
> 日期：2026-06-02

---

## 0. 设计原则

本设计遵循以下原则：

1. **模块独立性**：每个模块只通过构造函数参数了解其依赖，不依赖全局状态。测试时可以直接构造对象，手动替换依赖。
2. **Bus 是纯路由器**：Bus 不持有任何设备状态，只负责地址解码和数据转发。所有设备通过构造函数注入。
3. **单向数据流**：CPU → Bus → 设备，PPU → PPUBus → 设备。不存在循环依赖。
4. **可测试性**：每个类都可以独立实例化（注入 Mock 或测试替身），公开方法可直接测试。

---

## 1. 模块依赖关系图

```
                    ┌─────────────┐
                    │  Emulator   │  组装者：连接所有模块
                    └──────┬──────┘
                           │ 创建并注入
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
    │    Bus    │   │  PPUBus   │   │  Renderer │
    │ (CPU总线) │   │ (PPU总线) │   │  (Tkinter)│
    └─────┬─────┘   └─────┬─────┘   └───────────┘
          │                │
    ┌─────┴─────┐   ┌─────┴─────┐
    │    CPU    │   │    PPU    │
    │   6502    │   │  图形处理  │
    └───────────┘   └───────────┘

    注入到 Bus 的设备：
    ┌──────────────────────────────────────┐
    │  RAM (bytearray, 直接持有)            │
    │  Cartridge (cpu_read/cpu_write)      │
    │  PPU (cpu_read/cpu_write)            │
    │  Controller (read/write)             │
    └──────────────────────────────────────┘

    注入到 PPUBus 的设备：
    ┌──────────────────────────────────────┐
    │  Cartridge (ppu_read/ppu_write)      │
    │  Nametable RAM (bytearray, 直接持有)  │
    └──────────────────────────────────────┘
```

**关键设计**：Bus 和 PPUBus 不知道具体设备类型，只调用注入对象的 `read`/`write` 方法。CPU 和 PPU 也不直接引用 Bus 的具体实现，只通过构造函数传入的总线对象读写数据。

---

## 2. CPU 模块详细设计 (`cpu.py`)

### 2.1 指令组织方式：函数表 + match-case 分发

6502 有 256 个可能的操作码（0x00-0xFF），其中 151 条是官方指令。设计使用两层查找表：

```
第一层：操作码 → (指令函数, 寻址模式函数, 周期数)
第二层：指令函数内部用 match-case 处理具体逻辑
```

**为什么用函数表而不是一个大 match-case**：
- 函数表将 256 个操作码映射到约 56 个指令函数 + 13 个寻址模式函数
- 每个指令函数和寻址模式函数都是独立的小函数，便于单独测试
- 添加非官方指令只需扩展映射表，不修改已有函数

### 2.2 数据结构设计

```
class CPU6502:
    # ── 寄存器（全部用 int，Python 原生支持大整数）──
    a: int        # 累加器，0-255
    x: int        # X 寄存器，0-255
    y: int        # Y 寄存器，0-255
    sp: int       # 栈指针，0-255（实际地址 = 0x0100 | sp）
    pc: int       # 程序计数器，0-65535
    status: int   # 状态寄存器，0-255（每位代表一个标志）

    # ── 运行状态 ──
    cycles: int           # 已消耗的总周期数
    bus: Bus              # 总线引用（通过构造函数注入）
    interrupt_pending: int  # 待处理的中断类型（0=无, 1=NMI, 2=IRQ）

    # ── 指令查找表（类级别，所有实例共享）──
    # 在类初始化时构建，映射 opcode → InstructionEntry
    OPCODE_TABLE: dict[int, InstructionEntry]
```

**InstructionEntry 是什么**：一个简单数据结构，包含三个字段：
- `operation`: 指令执行函数的引用（如 `_op_lda`, `_op_sta`）
- `addressing`: 寻址模式函数的引用（如 `_addr_immediate`, `_addr_zero_page`）
- `base_cycles`: 基础周期数

### 2.3 寻址模式实现

每种寻址模式是一个独立函数，返回**操作数地址**和**是否跨页**的信息：

```
# 伪代码示例
def _addr_immediate(self) -> tuple[int, bool]:
    """立即寻址：操作数就是 PC 下一个字节"""
    addr = self.pc
    self.pc += 1
    return addr, False   # 地址, 是否跨页

def _addr_zero_page(self) -> tuple[int, bool]:
    """零页寻址：操作数地址在 0x00-0xFF"""
    addr = self._read(self.pc) & 0xFF
    self.pc += 1
    return addr, False

def _addr_absolute_x(self) -> tuple[int, bool]:
    """绝对X寻址：16位地址 + X偏移"""
    base = self._read_word(self.pc)
    self.pc += 2
    addr = (base + self.x) & 0xFFFF
    crossed_page = (base & 0xFF00) != (addr & 0xFF00)
    return addr, crossed_page
```

**跨页检测**：某些指令在地址跨越 256 字节边界时需要额外 1 个周期。寻址模式函数返回 `crossed_page` 标志，指令函数据此增加周期。

### 2.4 指令执行实现

每条指令是一个独立函数，接收操作数地址，执行逻辑，更新标志位：

```
# 伪代码示例
def _op_lda(self, addr: int, crossed_page: bool) -> int:
    """LDA - 将内存值加载到累加器"""
    self.a = self._read(addr)
    self._set_flag(Z_FLAG, self.a == 0)
    self._set_flag(N_FLAG, self.a & 0x80)
    return CROSS_PAGE_CYCLE if crossed_page else 0

def _op_adc(self, addr: int, crossed_page: bool) -> int:
    """ADC - 带进位加法"""
    value = self._read(addr)
    carry = self._get_flag(C_FLAG)
    result = self.a + value + carry

    self._set_flag(C_FLAG, result > 0xFF)
    self._set_flag(Z_FLAG, (result & 0xFF) == 0)
    self._set_flag(V_FLAG, (~(self.a ^ value) & (self.a ^ result) & 0x80) != 0)
    self._set_flag(N_FLAG, result & 0x80)

    self.a = result & 0xFF
    return CROSS_PAGE_CYCLE if crossed_page else 0
```

### 2.5 step() 方法的整体流程

```
def step(self) -> int:
    # 1. 检查是否有待处理的中断
    if self.interrupt_pending == NMI:
        self._handle_nmi()
        return NMI_CYCLES
    elif self.interrupt_pending == IRQ and not self._get_flag(I_FLAG):
        self._handle_irq()
        return IRQ_CYCLES

    # 2. 读取操作码
    opcode = self._read(self.pc)
    self.pc += 1

    # 3. 查找指令表
    entry = self.OPCODE_TABLE[opcode]

    # 4. 执行寻址模式，得到操作数地址
    addr, crossed_page = entry.addressing(self)

    # 5. 执行指令，得到额外周期
    extra_cycles = entry.operation(self, addr, crossed_page)

    # 6. 返回总周期数
    return entry.base_cycles + extra_cycles
```

### 2.6 中断处理

```
def _push(self, value: int):
    """压栈：写入 0x0100 + sp，sp 减 1"""
    self._write(0x0100 | self.sp, value & 0xFF)
    self.sp = (self.sp - 1) & 0xFF

def _handle_nmi(self):
    """NMI 处理流程"""
    self._push_word(self.pc)        # 压入 PC（高字节先）
    self._push(self.status)         # 压入状态寄存器
    self._set_flag(I_FLAG, True)    # 禁止中断
    self.pc = self._read_word(0xFFFA)  # 读取 NMI 向量
    self.interrupt_pending = 0

def reset(self):
    """复位流程：不压栈，只读取复位向量"""
    self.pc = self._read_word(0xFFFC)
    self.sp = 0xFD
    self.status = 0x24
    self.a = self.x = self.y = 0
```

### 2.7 CPU 与 Bus 的交互边界

CPU 只通过以下两个方法与外部交互：

```
def _read(self, address: int) -> int:
    """读一个字节，直接委托给 bus"""
    return self.bus.read(address)

def _write(self, address: int, value: int):
    """写一个字节，直接委托给 bus"""
    self.bus.write(address, value & 0xFF)
```

CPU **不知道** RAM 在哪里、PPU 寄存器怎么工作、卡带是什么格式。它只知道"给我一个地址，总线返回一个字节"。这使得 CPU 可以独立测试——只需注入一个简单的测试替身。

### 2.8 单元测试策略

```
测试 CPU 时，注入一个 MemoryStub：
- MemoryStub 是一个简单的 dict[int, int]，模拟内存
- 可以预设特定地址的值，验证 CPU 读写是否正确

测试用例示例：
- test_lda_immediate: 在地址 0x8000 放入 0xA9 0x42，执行一步，验证 a == 0x42
- test_adc_carry: 预设 a=0xFF, 内存值=0x01, 验证进位标志
- test_nmi: 触发 NMI，验证 PC 跳转到向量地址
```

---

## 3. PPU 模块详细设计 (`ppu.py`)

### 3.1 核心状态机

PPU 的行为由一个**状态机**驱动，状态由 `(scanline, cycle)` 二元组决定：

```
状态转换：

  (0, 0)         可见扫描线 0 开始
     ↓ 逐周期推进
  (0, 340)       扫描线 0 结束
     ↓
  (1, 0)         扫描线 1 开始
     ↓
  ...
     ↓
  (239, 340)     最后一条可见扫描线结束
     ↓
  (240, 0)       空闲扫描线
     ↓
  (241, 1)       VBlank 开始 → 设置标志 → 触发 NMI
     ↓
  ...
     ↓
  (260, 340)     VBlank 结束
     ↓
  (261, 0)       预渲染扫描线 → 重置 VBlank、精灵 0 碰撞
     ↓
  (261, 340)     帧结束 → scanline 重置为 0
```

### 3.2 渲染管线设计（扫描线级）

在扫描线级精度下，当 `scanline` 从 261 变为 0（或 cycle 到达特定点）时，一次性渲染整条扫描线的所有 256 个像素：

```
def _render_scanline(self, y: int):
    """渲染第 y 行的所有像素"""

    # 第一步：评估精灵
    # 遍历 OAM（64 个精灵），找出哪些精灵覆盖第 y 行
    visible_sprites = []
    for i in range(64):
        sprite_y = self.oam[i * 4]
        if sprite_y <= y < sprite_y + sprite_height:
            visible_sprites.append(i)
        if len(visible_sprites) >= 8:
            break  # 每行最多 8 个精灵

    # 第二步：逐像素合成
    for x in range(256):
        bg_color = self._get_background_pixel(x, y)   # 背景层
        spr_color, spr_priority = self._get_sprite_pixel(x, y, visible_sprites)  # 精灵层

        # 第三步：优先级合成
        final_color = self._composite(bg_color, spr_color, spr_priority)

        # 第四步：写入帧缓冲区
        self.framebuffer[y * 256 + x] = final_color
```

### 3.3 背景渲染详细流程

```
def _get_background_pixel(self, x: int, y: int) -> int:
    """
    获取 (x, y) 位置的背景颜色。

    步骤：
    1. 计算该像素在 Nametable 中对应的 Tile 坐标
       - tile_x = (x + scroll_x) // 8
       - tile_y = (y + scroll_y) // 8
       - 注意跨 Nametable 边界的情况

    2. 从 Nametable 读取 Tile 编号
       - nametable_addr = base_nametable + tile_y * 32 + tile_x
       - tile_index = ppu_bus.read(nametable_addr)

    3. 从 CHR-ROM 读取 Tile 的图案数据
       - 每个 Tile 占 16 字节（低平面 + 高平面）
       - pattern_addr = pattern_base + tile_index * 16
       - low_byte = ppu_bus.read(pattern_addr + fine_y)
       - high_byte = ppu_bus.read(pattern_addr + fine_y + 8)

    4. 合成 2-bit 像素值
       - bit0 = (low_byte >> (7 - fine_x)) & 1
       - bit1 = (high_byte >> (7 - fine_x)) & 1
       - color_index = bit1 << 1 | bit0

    5. 从 Attribute Table 读取调色板编号
       - attr_addr = 0x23C0 + (tile_y // 4) * 8 + (tile_x // 4)
       - attr_byte = ppu_bus.read(attr_addr)
       - 根据 (tile_y % 4, tile_x % 4) 提取 2-bit 调色板编号

    6. 返回最终颜色
       - palette_addr = 0x3F00 + palette_group * 4 + color_index
       - palette_index = ppu_bus.read(palette_addr)
       - return PALETTE_RGB[palette_index]
    """
```

### 3.4 精灵渲染详细流程

```
def _get_sprite_pixel(self, x: int, y: int, visible_sprites: list) -> tuple[int, int]:
    """
    获取 (x, y) 位置的精灵颜色。

    步骤：
    1. 遍历可见精灵列表（按优先级排序，索引越小优先级越高）
    2. 对每个精灵：
       - 读取 OAM 数据（4 字节）：sprite_y, tile_index, attributes, sprite_x
       - 检查 x 是否在精灵范围内
       - 从 CHR-ROM 读取图案数据
       - 处理水平/垂直翻转（attributes 的 bit 6/7）
       - 如果 color_index != 0（非透明），返回颜色

    3. 同时检测精灵 0 碰撞：
       - 如果精灵 0 的非透明像素与背景非透明像素重叠
       - 设置 PPUSTATUS 的精灵 0 碰撞标志
    """
```

### 3.5 PPU 寄存器读写设计

PPU 有几个"写两次"的寄存器（PPUSCROLL 和 PPUADDR），需要一个 `write_latch` 标志来跟踪当前是第一次还是第二次写入：

```
class PPU:
    # 写入状态
    write_latch: bool       # True=等待高字节, False=等待低字节
    scroll_x: int           # 水平滚动值（第一次写入 PPUSCROLL）
    scroll_y: int           # 垂直滚动值（第二次写入 PPUSCROLL）
    vram_addr_hi: int       # VRAM 地址高字节（第一次写入 PPUADDR）
    vram_addr_lo: int       # VRAM 地址低字节（第二次写入 PPUADDR）
    vram_addr: int          # 当前 VRAM 地址（14 位）
    read_buffer: int        # PPUDATA 预读缓冲区

    def cpu_write(self, address: int, value: int):
        match address:
            case 0x2000:  # PPUCTRL
                self.ctrl = value
                # 更新 nametable_base, pattern_base 等派生值

            case 0x2001:  # PPUMASK
                self.mask = value

            case 0x2005:  # PPUSCROLL
                if not self.write_latch:
                    self.scroll_x = value
                else:
                    self.scroll_y = value
                self.write_latch = not self.write_latch

            case 0x2006:  # PPUADDR
                if not self.write_latch:
                    self.vram_addr_hi = value & 0x3F
                else:
                    self.vram_addr_lo = value
                    self.vram_addr = (self.vram_addr_hi << 8) | self.vram_addr_lo
                self.write_latch = not self.write_latch

            case 0x2007:  # PPUDATA
                self.ppu_bus.write(self.vram_addr, value)
                self.vram_addr += self._addr_increment()

    def cpu_read(self, address: int) -> int:
        match address:
            case 0x2002:  # PPUSTATUS
                result = self.status
                self.status &= ~0x80       # 清除 VBlank 标志
                self.write_latch = False   # 重置写入锁存
                return result

            case 0x2007:  # PPUDATA
                value = self.read_buffer
                self.read_buffer = self.ppu_bus.read(self.vram_addr)
                # 调色板区域直接读取（不经过缓冲）
                if self.vram_addr >= 0x3F00:
                    value = self.read_buffer
                self.vram_addr += self._addr_increment()
                return value
```

### 3.6 NMI 触发机制

PPU 需要一种方式通知 CPU "VBlank 开始了"。设计中 PPU 持有一个**回调函数**：

```
class PPU:
    nmi_callback: callable  # 由 Emulator 注入，当 VBlank 开始时调用

    def tick(self):
        # ... 推进 cycle/scanline ...

        if self.scanline == 241 and self.cycle == 1:
            self.status |= 0x80  # 设置 VBlank 标志
            if self.ctrl & 0x80:  # 如果 NMI 使能
                if self.nmi_callback:
                    self.nmi_callback()  # 通知 CPU
```

**为什么用回调而不是让 CPU 轮询**：
- PPU 和 CPU 是并行运行的，CPU 不应该主动检查 PPU 状态
- 回调让 PPU 在正确的时间点通知 CPU，保持时序正确
- 测试时可以注入一个记录调用的 Mock 回调

### 3.7 PPU 与 PPUBus 的交互边界

PPU 通过 PPUBus 读取 CHR-ROM 和 Nametable，通过内部数组管理调色板和 OAM：

```
# PPU 的地址空间分为两部分：

# 1. PPUBus 管理的（外部设备）
#    0x0000-0x1FFF → CHR-ROM（通过 ppu_bus.read）
#    0x2000-0x2FFF → Nametable（通过 ppu_bus.read）

# 2. PPU 内部管理的
#    0x3F00-0x3F1F → 调色板 RAM（self.palette 数组）
#    OAM            → self.oam 数组（256 字节）
```

### 3.8 单元测试策略

```
测试 PPU 时，注入一个 PPUBusStub：
- PPUBusStub 内部是一个 dict[int, int]，模拟 CHR-ROM 和 Nametable
- 可以预设特定 Tile 图案数据，验证渲染结果

测试用例示例：
- test_vblank_flag: 执行 241*341 个 tick，验证 status 的 VBlank 标志被设置
- test_nmi_callback: 使能 NMI，执行到 VBlank，验证回调被调用
- test_background_pixel: 预设 Nametable 和 CHR-ROM，验证 _get_background_pixel 返回正确颜色
- test_sprite_evaluation: 预设 OAM，验证 _evaluate_sprites 返回正确列表
- test_scroll_register: 写入 PPUSCROLL 两次，验证 scroll_x 和 scroll_y
- test_vram_address_increment: 验证读/写 PPUDATA 后地址自动递增
```

---

## 4. Bus 模块详细设计 (`bus.py`)

### 4.1 纯路由器设计

Bus 是一个**纯地址解码器**，不持有任何设备的内部状态。它只知道"地址 X 应该转发给设备 Y"。

```
class Bus:
    # 所有设备通过构造函数注入
    ram: bytearray              # 2 KB RAM（Bus 直接持有，因为 RAM 就是一块内存）
    ppu: PPU                    # PPU 寄存器访问
    cartridge: Cartridge        # PRG-ROM 访问
    controller: Controller      # 手柄读写

    def read(self, address: int) -> int:
        """地址解码 + 路由读取"""
        address &= 0xFFFF  # 确保 16 位

        if address < 0x2000:
            # 0x0000-0x1FFF：RAM（含镜像）
            return self.ram[address & 0x07FF]

        elif address < 0x4000:
            # 0x2000-0x3FFF：PPU 寄存器（8 个寄存器，镜像到整个范围）
            return self.ppu.cpu_read(0x2000 + (address & 0x07))

        elif address == 0x4016:
            # 手柄 1
            return self.controller.read()

        elif address == 0x4017:
            # 手柄 2（暂不实现，返回 0）
            return 0

        elif address >= 0x4020:
            # 卡带空间
            return self.cartridge.cpu_read(address)

        else:
            # 0x4000-0x4015, 0x4018-0x401F：APU 寄存器（暂未实现）
            return 0

    def write(self, address: int, value: int):
        """地址解码 + 路由写入"""
        address &= 0xFFFF
        value &= 0xFF

        if address < 0x2000:
            self.ram[address & 0x07FF] = value

        elif address < 0x4000:
            self.ppu.cpu_write(0x2000 + (address & 0x07), value)

        elif address == 0x4014:
            # OAM DMA：将 CPU 内存的一页数据复制到 PPU 的 OAM
            # 这是一个特殊操作，需要 CPU 配合
            base_address = value << 8
            for i in range(256):
                self.ppu.oam[i] = self.read(base_address + i)

        elif address == 0x4016:
            self.controller.write(value)

        elif address >= 0x4020:
            self.cartridge.cpu_write(address, value)
```

### 4.2 地址镜像处理

FC 的地址空间有大量镜像（同一物理设备映射到多个地址）。Bus 在 `read`/`write` 中通过**位掩码**处理：

| 区域 | 镜像方式 | 处理方法 |
|------|----------|----------|
| RAM | 2 KB 镜像到 8 KB | `address & 0x07FF` |
| PPU 寄存器 | 8 字节镜像到 8 KB | `0x2000 + (address & 0x07)` |

### 4.3 单元测试策略

```
测试 Bus 时，注入 Mock 设备：

class MockPPU:
    def __init__(self):
        self.read_log = []   # 记录读取调用
        self.write_log = []  # 记录写入调用
    def cpu_read(self, addr):
        self.read_log.append(addr)
        return 0x42
    def cpu_write(self, addr, value):
        self.write_log.append((addr, value))

测试用例：
- test_ram_mirror: 写入 0x0000，读取 0x0800，应得到相同值
- test_ppu_register_mirror: 读取 0x3FF8，应路由到 PPU 的 0x2000
- test_oam_dma: 写入 0x4016，验证 controller.write 被调用
- test_cartridge_read: 读取 0x8000，验证 cartridge.cpu_read 被调用
```

---

## 5. PPUBus 模块设计 (`ppu_bus.py`)

### 5.1 设计思路

PPUBus 与 Bus 类似，也是纯路由器，管理 PPU 的 14 位地址空间（0x0000-0x3FFF）：

```
class PPUBus:
    cartridge: Cartridge        # CHR-ROM 访问
    nametable: bytearray        # 2 KB Nametable RAM
    mirror_mode: int            # 镜像模式（水平/垂直）

    def read(self, address: int) -> int:
        address &= 0x3FFF

        if address < 0x2000:
            # CHR-ROM
            return self.cartridge.ppu_read(address)

        elif address < 0x3F00:
            # Nametable（含镜像）
            return self.nametable[self._mirror_address(address)]

        # 0x3F00-0x3FFF 由 PPU 内部管理，不经过 PPUBus

    def _mirror_address(self, address: int) -> int:
        """将 Nametable 地址映射到 0-0xFFF 范围内"""
        addr = (address - 0x2000) % 0x1000
        table_index = addr // 0x0400   # 0-3，对应 4 个 Nametable 页面
        offset = addr % 0x0400         # 页面内偏移

        if self.mirror_mode == VERTICAL:
            # 垂直镜像：0=2, 1=3
            table_index &= 0x01
        elif self.mirror_mode == HORIZONTAL:
            # 水平镜像：0=1, 2=3
            table_index = (table_index >> 1) & 0x01

        return table_index * 0x0400 + offset
```

### 5.2 单元测试策略

```
测试 PPUBus 时：
- 预设 CHR-ROM 数据，验证 ppu_read 返回正确值
- 设置垂直镜像，验证 $2000 和 $2800 读取同一数据
- 设置水平镜像，验证 $2000 和 $2400 读取同一数据
```

---

## 6. Cartridge 模块设计 (`cartridge.py`)

### 6.1 ROM 解析流程

```
class Cartridge:
    prg_rom: bytearray
    chr_rom: bytearray
    mapper_id: int
    mirror_mode: int    # 0=水平, 1=垂直

    def __init__(self, rom_data: bytes):
        """
        接收 bytes 而不是文件路径，方便测试时直接传入构造的 ROM 数据。

        解析步骤：
        1. 验证前 4 字节 == b'NES\x1A'
        2. prg_banks = rom_data[4]
        3. chr_banks = rom_data[5]
        4. flag6 = rom_data[6]
           - mirror_mode = flag6 & 0x01
           - has_trainer = (flag6 >> 2) & 0x01
           - mapper_id 低 4 位 = flag6 >> 4
        5. flag7 = rom_data[7]
           - mapper_id 高 4 位 = flag7 & 0xF0
           - mapper_id = (flag7 & 0xF0) | (flag6 >> 4)
        6. 计算数据偏移：
           - offset = 16（header）
           - if has_trainer: offset += 512
        7. 读取 PRG-ROM：rom_data[offset : offset + prg_banks * 16384]
        8. 读取 CHR-ROM：紧接 PRG-ROM 之后
        """
```

### 6.2 Mapper 0 读取逻辑

```
def cpu_read(self, address: int) -> int:
    """Mapper 0 的 PRG-ROM 读取"""
    if address >= 0x8000:
        # 将 0x8000-0xFFFF 映射到 PRG-ROM 索引
        # Mapper 0 只有 16KB 或 32KB PRG-ROM
        index = (address - 0x8000) % len(self.prg_rom)
        return self.prg_rom[index]
    return 0

def ppu_read(self, address: int) -> int:
    """Mapper 0 的 CHR-ROM 读取"""
    if address < 0x2000 and len(self.chr_rom) > 0:
        return self.chr_rom[address % len(self.chr_rom)]
    return 0
```

### 6.3 单元测试策略

```
测试 Cartridge 时，构造最小 ROM 数据：
- 构造一个 16 字节 header + 32KB PRG-ROM + 8KB CHR-ROM 的 bytes
- 验证 mapper_id, mirror_mode, prg_rom, chr_rom 解析正确
- 验证 cpu_read(0x8000) 返回 prg_rom[0]
- 验证 ppu_read(0x0000) 返回 chr_rom[0]
- 验证非法魔数抛出异常
```

---

## 7. Controller 模块设计 (`input.py`)

### 7.1 串行读取协议

```
class Controller:
    button_state: int     # 8 位位掩码，每位对应一个按钮（1=按下）
    strobe: bool          # 锁存阶段标志
    bit_index: int        # 当前读取到第几位（0-7）

    KEY_MAP: dict = {
        'w': 4, 'Up': 4,       # 上
        's': 5, 'Down': 5,     # 下
        'a': 6, 'Left': 6,     # 左
        'd': 7, 'Right': 7,    # 右
        'j': 0, 'z': 0,        # A
        'k': 1, 'x': 1,        # B
        'Return': 3,            # Start
        'Shift_R': 2,           # Select
    }

    def write(self, value: int):
        """写入 $4016"""
        self.strobe = bool(value & 1)
        if self.strobe:
            self.bit_index = 0  # 锁存时重置读取位置

    def read(self) -> int:
        """读取 $4016"""
        if self.strobe:
            # 锁存期间始终返回 A 按钮状态
            return self.button_state & 1

        if self.bit_index < 8:
            result = (self.button_state >> self.bit_index) & 1
            self.bit_index += 1
        else:
            result = 1  # 超过 8 位后返回 1（FC 规范）
        return result

    def key_press(self, key: str):
        if key in self.KEY_MAP:
            self.button_state |= (1 << self.KEY_MAP[key])

    def key_release(self, key: str):
        if key in self.KEY_MAP:
            self.button_state &= ~(1 << self.KEY_MAP[key])
```

### 7.2 单元测试策略

```
测试用例：
- test_strobe_protocol: 写入 1 再写入 0，验证锁存和读取流程
- test_serial_read: 按下 A+Start，写入 1 再 0，连续读取 8 次，验证返回正确的位序列
- test_key_press_release: 模拟按键按下/释放，验证 button_state 变化
```

---

## 8. Renderer 模块设计 (`renderer.py`)

### 8.1 概要设计

Renderer 是唯一与 Tkinter 耦合的模块，负责：
1. 创建窗口和 Canvas
2. 接收帧缓冲区数据，转换为 PhotoImage 格式
3. 绑定键盘事件

```
class Renderer:
    root: tk.Tk
    canvas: tk.Canvas
    photo: tk.PhotoImage
    scale: int

    def __init__(self, title: str, scale: int):
        self.root = tk.Tk()
        self.root.title(title)
        self.scale = scale

        # 创建 PhotoImage（原始 256x240，缩放在 Canvas 上实现）
        self.photo = tk.PhotoImage(width=256, height=240)

        # 创建 Canvas
        self.canvas = tk.Canvas(
            self.root,
            width=256 * scale,
            height=240 * scale
        )
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.pack()

    def render_frame(self, framebuffer: list[int]):
        """
        将帧缓冲区渲染到 PhotoImage。

        性能优化：使用 put() 方法批量写入像素。
        put() 接受颜色字符串列表，比逐像素 put() 快得多。

        实现：
        for y in range(240):
            row_colors = []
            for x in range(256):
                rgb = framebuffer[y * 256 + x]
                r = (rgb >> 16) & 0xFF
                g = (rgb >> 8) & 0xFF
                b = rgb & 0xFF
                row_colors.append(f'#{r:02x}{g:02x}{b:02x}')
            # 每行用一个 put() 调用
            self.photo.put('{' + ' '.join(row_colors) + '}', to=(0, y))

        # 缩放到 Canvas
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo,
                                 scale=True)  # 需要实现缩放
        """

    def bind_key(self, key: str, callback: callable):
        """绑定键盘事件"""
        self.root.bind(f'<{key}>', callback)

    def schedule(self, delay_ms: int, callback: callable):
        """定时器：用于驱动帧循环"""
        self.root.after(delay_ms, callback)

    def start(self):
        """启动主循环"""
        self.root.mainloop()
```

### 8.2 帧率控制

使用 Tkinter 的 `after()` 方法实现帧率控制，而非实时循环：

```
# 在 Emulator 中：
def _frame_loop(self):
    """由 after() 驱动的帧循环"""
    self._run_frame()                       # 执行一帧
    self.renderer.render_frame(self.ppu.framebuffer)  # 渲染
    self.renderer.schedule(16, self._frame_loop)      # 约 60 FPS (16ms)
```

---

## 9. Emulator 组装设计 (`emulator.py`)

### 9.1 组装顺序

Emulator 是"组装者"，负责创建所有模块并正确连接它们：

```
class Emulator:
    def __init__(self, rom_path: str, scale: int = 3):
        # 第一步：加载 ROM
        with open(rom_path, 'rb') as f:
            rom_data = f.read()
        self.cartridge = Cartridge(rom_data)

        # 第二步：创建输入设备
        self.controller = Controller()

        # 第三步：创建 PPU 和 PPUBus
        self.ppu_bus = PPUBus(self.cartridge, self.cartridge.mirror_mode)
        self.ppu = PPU(self.ppu_bus)

        # 第四步：创建 CPU 和 Bus
        self.bus = Bus(ram=bytearray(2048), ppu=self.ppu,
                       cartridge=self.cartridge, controller=self.controller)
        self.cpu = CPU6502(self.bus)

        # 第五步：连接 PPU 的 NMI 回调到 CPU
        self.ppu.nmi_callback = self.cpu.nmi

        # 第六步：创建渲染器
        self.renderer = Renderer("PyFC - FC Emulator", scale)
        self.renderer.bind_key('<KeyPress>', self._on_key_press)
        self.renderer.bind_key('<KeyRelease>', self._on_key_release)

        # 第七步：复位所有组件
        self.cpu.reset()
        self.ppu.reset()
```

### 9.2 主循环流程

```
def _run_frame(self):
    """执行一帧的 CPU/PPU 周期"""
    self.ppu.frame_complete = False

    while not self.ppu.frame_complete:
        # CPU 执行一条指令
        cpu_cycles = self.cpu.step()

        # 同步推进 PPU（1 CPU 周期 = 3 PPU 周期）
        for _ in range(cpu_cycles * 3):
            self.ppu.tick()
            if self.ppu.frame_complete:
                break
```

### 9.3 输入事件处理

```
def _on_key_press(self, event):
    """键盘按下事件 → 转发给 Controller"""
    self.controller.key_press(event.keysym)

def _on_key_release(self, event):
    """键盘释放事件 → 转发给 Controller"""
    self.controller.key_release(event.keysym)
```

---

## 10. 模块独立性总结

| 模块 | 依赖 | 可替换的依赖 | 测试时如何隔离 |
|------|------|-------------|----------------|
| CPU | Bus | Bus（任何有 read/write 的对象） | 注入 MemoryStub |
| PPU | PPUBus, nmi_callback | PPUBus, callback | 注入 PPUBusStub + Mock 回调 |
| Bus | RAM, PPU, Cartridge, Controller | 全部可替换 | 注入 Mock 设备 |
| PPUBus | Cartridge, mirror_mode | Cartridge | 注入 Mock Cartridge |
| Cartridge | 无（接收 bytes） | 无 | 直接构造测试 ROM bytes |
| Controller | 无 | 无 | 直接实例化测试 |
| Renderer | Tkinter | 无（UI 组件难以 Mock） | 集成测试，不单元测试 |
| Emulator | 全部 | 全部 | 不单独测试，依赖各模块正确 |

**核心设计保证**：CPU、PPU、Bus、Cartridge、Controller 这 5 个核心模块都可以**零外部依赖**地进行单元测试（只需 Python 标准库 + pytest）。
