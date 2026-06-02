# FC 模拟器需求文档

> 项目名称：PyFC（Python FC Emulator）
> 目标：使用 Python 实现一个能运行《超级玛丽》的 FC/NES 模拟器（学习项目）
> Python 版本：3.12+
> 图形库：Tkinter
> 文档版本：v1.0
> 日期：2026-06-02

---

## 1. FC/NES 硬件背景知识

> 本章为完全不了解模拟器开发的读者准备，详细解释 FC 的硬件组成和工作原理。

### 1.1 什么是 FC/NES

FC（Family Computer）是任天堂于 1983 年推出的 8 位家用游戏机，在中国俗称"红白机"。NES（Nintendo Entertainment System）是其北美版本。它是一个**固定硬件平台**，所有 FC 游戏都是为这套固定硬件编写的程序。

### 1.2 FC 的核心硬件组件

FC 内部由以下核心组件构成，模拟器就是要用软件重现每个组件的行为：

```
┌─────────────────────────────────────────────────────┐
│                    FC 主板                            │
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  │   CPU    │   │   PPU    │   │   APU    │        │
│  │  6502    │   │ 图形处理  │   │ 声音处理  │        │
│  │  8位处理器│   │  显示单元  │   │ 音频单元  │        │
│  └────┬─────┘   └────┬─────┘   └──────────┘        │
│       │              │                               │
│  ┌────┴──────────────┴────┐                         │
│  │        主内存 (RAM)     │                         │
│  │        2 KB             │                         │
│  └─────────────────────────┘                         │
│                                                      │
│  ┌─────────────────────────┐   ┌─────────────────┐  │
│  │      卡带 (Cartridge)    │   │   输入设备       │  │
│  │  ┌─────┐ ┌─────┐        │   │  手柄1  手柄2    │  │
│  │  │PRG- │ │CHR- │        │   └─────────────────┘  │
│  │  │ROM  │ │ROM  │        │                         │
│  │  │程序  │ │图形  │        │                         │
│  │  └─────┘ └─────┘        │                         │
│  └─────────────────────────┘                         │
└─────────────────────────────────────────────────────┘
```

#### 1.2.1 CPU — 中央处理器（MOS 6502）

- **型号**：MOS Technology 6502（8 位处理器）
- **主频**：1.789773 MHz（NTSC 制式）
- **寻址范围**：64 KB（地址总线 16 位，0x0000 - 0xFFFF）
- **寄存器**：
  - `A`（累加器）：算术和逻辑运算的主要寄存器
  - `X`（索引寄存器 X）：循环计数、偏移寻址
  - `Y`（索引寄存器 Y）：同上
  - `SP`（栈指针）：指向栈空间（0x0100-0x01FF）
  - `PC`（程序计数器）：指向下一条要执行的指令地址
  - `P`（状态寄存器）：包含零标志(Z)、进位(C)、负数(N)、溢出(V)等标志位
- **指令集**：56 条指令，有多种寻址模式（立即寻址、零页寻址、绝对寻址、间接寻址等）

**CPU 内存映射**（CPU 能看到的 64 KB 地址空间）：

| 地址范围 | 大小 | 用途 |
|----------|------|------|
| 0x0000-0x07FF | 2 KB | 内部 RAM |
| 0x0800-0x1FFF | — | RAM 的镜像（重复映射） |
| 0x2000-0x2007 | 8 字节 | PPU 寄存器 |
| 0x2008-0x3FFF | — | PPU 寄存器的镜像 |
| 0x4000-0x4017 | 24 字节 | APU 和 I/O 寄存器 |
| 0x4018-0x401F | — | 通常未使用 |
| 0x4020-0xFFFF | ~48 KB | 卡带空间（PRG-ROM、SRAM 等） |

#### 1.2.2 PPU — 图形处理单元（Picture Processing Unit）

PPU 负责生成 FC 的画面输出，是模拟器中最复杂的部分之一。

- **分辨率**：256 × 240 像素
- **色彩**：从 64 色调色板中选 25 色同时显示（背景 13 色 + 精灵 12 色）
- **帧率**：60 FPS（NTSC）/ 50 FPS（PAL）

**PPU 的核心概念**：

**① Tile（图块）**

FC 的画面不是逐像素绘制的，而是由 8×8 像素的小图块拼成的。每个 Tile 使用 2 bit 色深（每个像素 4 种颜色之一，其中颜色 0 为透明）。

**② 背景层（Background / Nametable）**

- 整个画面由 30×32 = 960 个 Tile 组成背景
- 使用 **Nametable**（名称表）存储每个位置放哪个 Tile
- Nametable 大小为 2 KB（0x2000-0x2FFF），有 4 个页面但通常镜像为 2 个
- **Attribute Table**：每个 4×4 Tile 区域共享一个调色板（节省内存）

**③ 精灵层（Sprites / OAM）**

- FC 支持 64 个精灵（活动对象），每个精灵 8×8 或 8×16 像素
- 每行最多显示 8 个精灵（超出会闪烁）
- **OAM（Object Attribute Memory）**：256 字节，存储所有精灵的属性
  - 每个精灵 4 字节：Y 坐标、Tile 编号、属性（翻转/调色板）、X 坐标

**④ 调色板（Palette）**

- FC 有一个 64 色的系统调色板（硬件固定）
- 游戏通过索引选择颜色：
  - 背景调色板：0x3F00-0x3F0F（4 组，每组 4 色）
  - 精灵调色板：0x3F10-0x3F1F（4 组，每组 4 色）

**⑤ 渲染流程**

PPU 逐行扫描渲染，每帧 262 条扫描线：

```
扫描线 0-239：   可见区域，渲染背景和精灵
扫描线 240：     空闲
扫描线 241-260： 垂直消隐期（VBlank）
扫描线 261：     预渲染行
```

在 VBlank 期间，CPU 可以安全地更新 PPU 的数据（修改画面）。

**⑥ Mapper（内存映射器）**

早期 FC 卡带只有 32 KB PRG-ROM 和 8 KB CHR-ROM。后来的游戏需要更大的 ROM，就通过 Mapper 芯片来切换不同的 ROM 银行（Bank Switching）。超级玛丽使用的是 **Mapper 0（NROM）**，最简单的映射方式，无需切换。

#### 1.2.3 APU — 音频处理单元（Audio Processing Unit）

负责声音输出。本次开发**第一版不实现**，在需求文档中预留接口。

APU 提供 5 个声道：
- 2 个脉冲波声道（Pulse）
- 1 个三角波声道（Triangle）
- 1 个噪声声道（Noise）
- 1 个 DMC 采样声道（Delta Modulation Channel）

#### 1.2.4 输入系统

FC 有两个手柄接口，每个手柄有 8 个按钮：

| 位 | 按钮 |
|----|------|
| 0 | A |
| 1 | B |
| 2 | Select |
| 3 | Start |
| 4 | 上 |
| 5 | 下 |
| 6 | 左 |
| 7 | 右 |

手柄通过 $4016/$4017 端口读取，使用**串行移位**方式：写 1 再写 0 到端口锁存按钮状态，然后逐位读取。

### 1.3 ROM 文件格式（iNES）

超级玛丽等 FC 游戏以 `.nes` 文件存储，使用 iNES 格式：

```
┌───────────────────────────────────┐
│  Header（16 字节）                 │
│  ├─ "NES\x1A" 魔数               │
│  ├─ PRG-ROM 银行数（×16 KB）      │
│  ├─ CHR-ROM 银行数（×8 KB）       │
│  ├─ Flag 6（Mapper 低4位 + 镜像） │
│  ├─ Flag 7（Mapper 高4位）        │
│  └─ 其他标志                      │
├───────────────────────────────────┤
│  Trainer（512 字节，可选）         │
├───────────────────────────────────┤
│  PRG-ROM（程序代码）              │
│  超级玛丽：2 × 16 KB = 32 KB     │
├───────────────────────────────────┤
│  CHR-ROM（图形数据）              │
│  超级玛丽：1 × 8 KB = 8 KB       │
└───────────────────────────────────┘
```

---

## 2. 功能需求

### 2.1 核心功能（第一版必须实现）

#### FR-01：ROM 加载
- 支持加载 `.nes` 格式的 ROM 文件
- 解析 iNES 文件头，提取 PRG-ROM、CHR-ROM、Mapper 编号、镜像方式等信息
- 根据 Mapper 编号选择对应的内存映射策略

#### FR-02：CPU 模拟
- 实现完整的 MOS 6502 指令集（151 条官方指令 + 常见非官方指令）
- 支持所有寻址模式：立即、零页、零页X/Y、绝对、绝对X/Y、间接、X间接、Y间接、相对、隐含
- 正确实现中断：NMI（不可屏蔽中断）、IRQ（中断请求）、Reset
- 周期精确：每条指令消耗正确的 CPU 周期数

#### FR-03：PPU 模拟
- 实现 PPU 寄存器读写（$2000-$2007）
- 实现背景渲染：Nametable 读取、Attribute Table、滚动（Scroll）
- 实现精灵渲染：OAM 读取、精灵优先级、精灵 0 碰撞检测
- 实现调色板管理
- 正确的渲染时序：扫描线级别精度
- VBlank 标志和 NMI 触发

#### FR-04：内存映射
- 实现 CPU 地址空间的完整映射
- 实现 PPU 地址空间的映射（调色板、Nametable 镜像）
- 支持 Mapper 0（NROM），超级玛丽使用的映射器

#### FR-05：输入处理
- 键盘映射到 FC 手柄按钮
- 实现 $4016 端口的手柄读取协议（锁存 + 串行读取）
- 默认键位配置：
  - `W/A/S/D` 或 `方向键` → 方向
  - `J` / `Z` → A 按钮
  - `K` / `X` → B 按钮
  - `Enter` → Start
  - `Right Shift` → Select

#### FR-06：画面渲染
- 使用 Tkinter Canvas 渲染 256×240 画面
- 支持缩放显示（建议 2x 或 3x，即 512×480 或 768×720）
- 维持 60 FPS 的帧率（或尽可能接近）

### 2.2 扩展功能（后续版本实现）

#### FR-07：APU 声音模拟（低优先级）
- 实现 5 个声道的基本音频合成
- 使用 Python 音频库输出

#### FR-08：即时存档（低优先级）
- 保存完整的模拟器状态（CPU 寄存器、内存、PPU 状态）到文件
- 从文件恢复状态
- 支持多个存档槽位

#### FR-09：更多 Mapper 支持（低优先级）
- Mapper 1（MMC1）
- Mapper 2（UxROM）
- Mapper 4（MMC3）

---

## 3. 技术架构

### 3.1 整体架构

采用**模块化分层架构**，每个硬件组件对应一个独立模块，通过明确定义的接口通信。

```
┌─────────────────────────────────────────────────────────┐
│                    主循环 (Main Loop)                     │
│                    main.py / emulator.py                 │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Bus（总线 / 地址空间）                 │   │
│  │         负责地址解码和数据路由                      │   │
│  │                                                    │   │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐         │   │
│  │  │ CPU  │  │ PPU  │  │ APU  │  │ Input│         │   │
│  │  │6502  │  │      │  │(预留)│  │      │         │   │
│  │  └──────┘  └──────┘  └──────┘  └──────┘         │   │
│  │                                                    │   │
│  │  ┌──────────────────┐  ┌────────────────────┐    │   │
│  │  │   Cartridge      │  │    RAM (2 KB)      │    │   │
│  │  │   (ROM Loader)   │  │                    │    │   │
│  │  └──────────────────┘  └────────────────────┘    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────┐                                   │
│  │   Renderer       │   ← 读取 PPU 的帧缓冲区           │
│  │   (Tkinter)      │   → 渲染到 Canvas                 │
│  └──────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

### 3.2 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 主循环 | `emulator.py` | 协调各模块，控制帧率，驱动主循环 |
| CPU | `cpu.py` | 6502 指令解码与执行、寄存器管理、中断处理 |
| PPU | `ppu.py` | 图形渲染、寄存器管理、精灵/背景绘制 |
| 总线 | `bus.py` | CPU 地址空间映射、读写路由 |
| PPU 总线 | `ppu_bus.py` | PPU 地址空间映射 |
| 卡带 | `cartridge.py` | ROM 文件解析、Mapper 实现 |
| 输入 | `input.py` | 键盘事件捕获、手柄协议模拟 |
| 渲染器 | `renderer.py` | Tkinter 窗口管理、Canvas 渲染、帧率控制 |
| 调色板 | `palette.py` | FC 系统调色板数据（64 色 RGB 映射表） |
| 主入口 | `main.py` | 程序入口，命令行参数解析 |

### 3.3 数据流

```
每帧执行流程：

1. CPU 执行指令
   │
   ├─ 读/写内存 → Bus → 路由到 RAM / PPU寄存器 / APU / Input / Cartridge
   │
   ├─ 如果写入 PPU 寄存器 → PPU 更新内部状态
   │
   └─ 每条指令消耗 N 个 CPU 周期
       │
       └─ 每个 CPU 周期 → PPU 推进 3 个 PPU 周期（1:3 时钟比）
           │
           └─ PPU 每个周期处理一个像素
               │
               ├─ 到达扫描线 241 → 设置 VBlank 标志 → 触发 NMI
               │
               └─ 到达扫描线 261 → 重置 VBlank → 开始新帧
                   │
                   └─ Renderer 读取帧缓冲区 → 渲染到 Canvas
```

### 3.4 关键技术决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| 渲染精度 | 扫描线级 | 像素级精度太慢，扫描线级足以运行超级玛丽 |
| 帧同步 | Tkinter after() | 使用 Tkinter 的定时器而非实时循环，避免阻塞 UI |
| Python 版本 | 3.12+ | 使用 match-case 等新特性简化指令解码 |
| Mapper | 仅 Mapper 0 | 超级玛丽使用 Mapper 0，最简单，适合学习 |
| 代码风格 | 类型注解 + 文档字符串 | 学习项目，可读性优先 |

---

## 4. 模块接口设计

### 4.1 CPU 模块 (`cpu.py`)

```python
class CPU6502:
    """MOS 6502 CPU 模拟器"""

    # === 寄存器 ===
    a: int          # 累加器 (8 bit)
    x: int          # X 索引寄存器 (8 bit)
    y: int          # Y 索引寄存器 (8 bit)
    sp: int         # 栈指针 (8 bit), 实际地址 = 0x0100 + sp
    pc: int         # 程序计数器 (16 bit)
    status: int     # 状态寄存器 (8 bit), 各标志位
    cycles: int     # 已消耗的周期计数

    # === 标志位常量 ===
    C_FLAG = 0  # 进位
    Z_FLAG = 1  # 零
    I_FLAG = 2  # 中断禁止
    D_FLAG = 3  # 十进制模式（FC 未使用）
    B_FLAG = 4  # BRK 指令
    V_FLAG = 6  # 溢出
    N_FLAG = 7  # 负数

    def __init__(self, bus: 'Bus'):
        """
        Args:
            bus: CPU 总线实例，用于内存读写
        """
        ...

    def reset(self) -> None:
        """复位 CPU：读取 0xFFFC-0xFFFD 的复位向量，初始化寄存器"""
        ...

    def step(self) -> int:
        """
        执行一条指令。

        Returns:
            本条指令消耗的 CPU 周期数

        流程：
        1. 从 PC 读取操作码
        2. 解码操作码 → 确定指令 + 寻址模式
        3. 计算操作数地址（根据寻址模式）
        4. 执行指令
        5. 返回周期数
        """
        ...

    def nmi(self) -> None:
        """触发 NMI（不可屏蔽中断）：保存现场，跳转到 NMI 向量（0xFFFA）"""
        ...

    def irq(self) -> None:
        """触发 IRQ（中断请求）：如果 I 标志未设置，保存现场并跳转到 IRQ 向量（0xFFFE）"""
        ...

    def _read(self, address: int) -> int:
        """通过总线读取一个字节"""
        ...

    def _write(self, address: int, value: int) -> None:
        """通过总线写入一个字节"""
        ...

    def _get_flag(self, flag: int) -> int:
        """获取状态寄存器中指定位的值"""
        ...

    def _set_flag(self, flag: int, value: bool) -> None:
        """设置状态寄存器中指定位的值"""
        ...
```

**支持的寻址模式**：

| 寻址模式 | 语法示例 | 说明 |
|----------|----------|------|
| Implicit | `NOP` | 无操作数 |
| Accumulator | `LSR A` | 操作累加器 |
| Immediate | `LDA #$10` | 操作数就是指令的一部分 |
| Zero Page | `LDA $10` | 地址在 0x00-0xFF 内 |
| Zero Page,X | `LDA $10,X` | 零页地址 + X 偏移 |
| Zero Page,Y | `LDA $10,Y` | 零页地址 + Y 偏移 |
| Absolute | `LDA $1234` | 16 位绝对地址 |
| Absolute,X | `LDA $1234,X` | 绝对地址 + X 偏移 |
| Absolute,Y | `LDA $1234,Y` | 绝对地址 + Y 偏移 |
| Indirect | `JMP ($1234)` | 间接跳转 |
| (Indirect,X) | `LDA ($10,X)` | X 间接寻址 |
| (Indirect),Y | `LDA ($10),Y` | Y 间接寻址 |
| Relative | `BEQ label` | 相对分支（-128 ~ +127） |

### 4.2 PPU 模块 (`ppu.py`)

```python
class PPU:
    """PPU（图形处理单元）模拟器"""

    # === PPU 寄存器（CPU 侧视角，映射到 $2000-$2007）===
    ctrl: int       # $2000 PPUCTRL - 控制寄存器
    mask: int       # $2001 PPUMASK - 遮罩寄存器
    status: int     # $2002 PPUSTATUS - 状态寄存器
    oam_addr: int   # $2003 OAMADDR - OAM 地址
    oam_data: int   # $2004 OAMDATA - OAM 数据
    scroll: int     # $2005 PPUSCROLL - 滚动偏移
    addr: int       # $2006 PPUADDR - VRAM 地址
    data: int       # $2007 PPUDATA - VRAM 数据

    # === 内部状态 ===
    oam: bytearray          # OAM 内存 (256 字节)
    vram: bytearray         # VRAM 内存 (2 KB)
    palette: bytearray      # 调色板 RAM (32 字节)
    framebuffer: list       # 帧缓冲区 (256 × 240 像素的 RGB 值)
    scanline: int           # 当前扫描线 (0-261)
    cycle: int              # 当前周期 (0-340)
    frame_complete: bool    # 一帧是否渲染完成

    def __init__(self, ppu_bus: 'PPUBus'):
        """
        Args:
            ppu_bus: PPU 总线实例，用于读取 CHR-ROM 和 Nametable
        """
        ...

    def reset(self) -> None:
        """复位 PPU 所有寄存器和状态"""
        ...

    def tick(self) -> None:
        """
        推进一个 PPU 周期。

        流程：
        1. 根据当前 scanline 和 cycle 判断处于哪个阶段
        2. 可见区域（scanline 0-239）：渲染背景和精灵像素
        3. scanline 241, cycle 1：设置 VBlank 标志，触发 NMI
        4. 扫描线 261：预渲染，重置 VBlank
        """
        ...

    def cpu_read(self, address: int) -> int:
        """
        CPU 读取 PPU 寄存器。

        Args:
            address: CPU 地址（$2000-$2007，会被镜射到这个范围）
        Returns:
            寄存器的值
        特殊：
            - 读 $2002 会清除 VBlank 标志
            - 读 $2007 会从 VRAM 预读取
        """
        ...

    def cpu_write(self, address: int, value: int) -> None:
        """
        CPU 写入 PPU 寄存器。

        Args:
            address: CPU 地址（$2000-$2007）
            value: 要写入的值
        """
        ...

    def _render_scanline(self) -> None:
        """渲染当前扫描线的所有像素（背景 + 精灵）"""
        ...

    def _get_background_pixel(self) -> tuple[int, int]:
        """
        获取当前像素的背景颜色。

        Returns:
            (palette_index, color_index) - 调色板组号和颜色号
        """
        ...

    def _get_sprite_pixel(self) -> tuple[int, int, int]:
        """
        获取当前像素的精灵颜色。

        Returns:
            (palette_index, color_index, priority) - 调色板、颜色、优先级
        """
        ...

    def _evaluate_sprites(self) -> list:
        """
        评估当前扫描线有哪些精灵可见。

        Returns:
            当前行可见精灵列表（最多 8 个）
        """
        ...
```

**PPU 寄存器说明**：

| 地址 | 名称 | 读/写 | 说明 |
|------|------|-------|------|
| $2000 | PPUCTRL | 写 | NMI 使能、精灵大小、背景 Tile 表地址等 |
| $2001 | PPUMASK | 写 | 显示使能、颜色模式、精灵/背景显示开关 |
| $2002 | PPUSTATUS | 读 | VBlank 标志、精灵 0 碰撞、精灵溢出 |
| $2003 | OAMADDR | 写 | OAM 读写地址 |
| $2004 | OAMDATA | 读/写 | OAM 数据 |
| $2005 | PPUSCROLL | 写 ×2 | 水平/垂直滚动（两次写入） |
| $2006 | PPUADDR | 写 ×2 | VRAM 地址（两次写入：高字节、低字节） |
| $2007 | PPUDATA | 读/写 | VRAM 数据（读写后地址自动递增） |

### 4.3 Bus 模块 (`bus.py`)

```python
class Bus:
    """CPU 总线 —— 管理 CPU 的 64 KB 地址空间"""

    ram: bytearray              # 2 KB 内部 RAM
    cpu: CPU6502                # CPU 引用（用于周期同步）
    ppu: PPU                    # PPU 引用（寄存器访问）
    cartridge: Cartridge        # 卡带引用（PRG-ROM 访问）
    controller: Controller      # 输入设备引用

    def __init__(self):
        ...

    def read(self, address: int) -> int:
        """
        从指定地址读取一个字节。

        地址解码逻辑：
        - 0x0000-0x1FFF → RAM（含镜像）
        - 0x2000-0x3FFF → PPU 寄存器（含镜像）
        - 0x4016        → 手柄 1 读取
        - 0x4017        → 手柄 2 读取
        - 0x4020-0xFFFF → 卡带空间

        Args:
            address: 16 位地址
        Returns:
            该地址处的字节值
        """
        ...

    def write(self, address: int, value: int) -> None:
        """
        向指定地址写入一个字节。

        地址解码逻辑同 read()。

        Args:
            address: 16 位地址
            value: 要写入的字节值（0-255）
        """
        ...
```

### 4.4 PPU Bus 模块 (`ppu_bus.py`)

```python
class PPUBus:
    """PPU 总线 —— 管理 PPU 的地址空间"""

    cartridge: Cartridge        # 卡带（CHR-ROM 访问）
    nametable: bytearray        # 2 KB Nametable RAM
    mirror_mode: int            # 镜像模式（水平/垂直）

    def __init__(self, cartridge: Cartridge):
        ...

    def read(self, address: int) -> int:
        """
        PPU 地址空间读取。

        地址解码逻辑：
        - 0x0000-0x1FFF → CHR-ROM（卡带提供）
        - 0x2000-0x3FFF → Nametable（含镜像）
        - 0x3F00-0x3F1F → 调色板（由 PPU 内部管理）

        Args:
            address: 14 位 PPU 地址
        Returns:
            字节值
        """
        ...

    def write(self, address: int, value: int) -> None:
        """
        PPU 地址空间写入。

        Args:
            address: 14 位 PPU 地址
            value: 字节值
        """
        ...

    def _mirror_address(self, address: int) -> int:
        """
        根据镜像模式将 Nametable 地址映射到实际物理地址。

        水平镜像：$2000=$2400, $2800=$2C00
        垂直镜像：$2000=$2800, $2400=$2C00

        Args:
            address: Nametable 区域地址
        Returns:
            映射后的实际地址
        """
        ...
```

### 4.5 Cartridge 模块 (`cartridge.py`)

```python
class Cartridge:
    """卡带模拟器 —— ROM 加载和 Mapper 管理"""

    prg_rom: bytearray      # 程序 ROM 数据
    chr_rom: bytearray      # 图形 ROM 数据
    mapper_id: int          # Mapper 编号（0=NROM）
    mirror_mode: int        # 镜像方式
    prg_banks: int          # PRG-ROM 银行数
    chr_banks: int          # CHR-ROM 银行数

    def __init__(self, rom_path: str):
        """
        加载并解析 .nes ROM 文件。

        Args:
            rom_path: .nes 文件路径

        解析流程：
        1. 验证文件头魔数 "NES\x1A"
        2. 读取 PRG-ROM 和 CHR-ROM 银行数
        3. 解析 Mapper 编号和镜像方式
        4. 跳过 Trainer（如有）
        5. 读取 PRG-ROM 数据
        6. 读取 CHR-ROM 数据
        """
        ...

    def cpu_read(self, address: int) -> int:
        """
        CPU 侧读取（PRG-ROM 空间）。

        Mapper 0 实现：
        - 如果只有 1 个 16KB 银行，映射到 $8000-$BFFF 和 $C000-$FFFF（镜像）
        - 如果有 2 个 16KB 银行，$8000-$BFFF = 银行0，$C000-$FFFF = 银行1

        Args:
            address: CPU 地址（0x8000-0xFFFF）
        Returns:
            字节值
        """
        ...

    def cpu_write(self, address: int, value: int) -> None:
        """
        CPU 侧写入。Mapper 0 不支持写入 PRG-ROM，忽略。

        Args:
            address: CPU 地址
            value: 字节值
        """
        ...

    def ppu_read(self, address: int) -> int:
        """
        PPU 侧读取（CHR-ROM 空间）。

        Args:
            address: PPU 地址（0x0000-0x1FFF）
        Returns:
            字节值
        """
        ...

    def ppu_write(self, address: int, value: int) -> None:
        """
        PPU 侧写入。Mapper 0 使用 CHR-ROM（只读），忽略写入。
        """
        ...
```

### 4.6 Input 模块 (`input.py`)

```python
class Controller:
    """手柄控制器模拟"""

    # 按钮常量
    BUTTON_A      = 0
    BUTTON_B      = 1
    BUTTON_SELECT = 2
    BUTTON_START  = 3
    BUTTON_UP     = 4
    BUTTON_DOWN   = 5
    BUTTON_LEFT   = 6
    BUTTON_RIGHT  = 7

    # 键位映射表
    KEY_MAP: dict[str, int]  # 键盘按键 → FC 按钮

    button_state: int    # 当前按钮状态（8 位位掩码）
    strobe: bool         # 锁存标志
    shift_register: int  # 移位寄存器（用于串行读取）

    def __init__(self):
        """
        初始化键位映射：
        - W / Up     → 上
        - S / Down   → 下
        - A / Left   → 左
        - D / Right  → 右
        - J / Z      → A
        - K / X      → B
        - Enter      → Start
        - Right Shift → Select
        """
        ...

    def write(self, value: int) -> None:
        """
        写入 $4016 端口（锁存按钮状态）。

        协议：
        - 写入 1：锁存当前按钮状态到移位寄存器
        - 写入 0：开始串行读取模式

        Args:
            value: 写入值（只看 bit 0）
        """
        ...

    def read(self) -> int:
        """
        读取 $4016 端口（串行读取按钮状态）。

        Returns:
            0 或 1，表示当前位的按钮状态
        读取后自动移位到下一位。
        """
        ...

    def key_press(self, key: str) -> None:
        """键盘按下事件处理"""
        ...

    def key_release(self, key: str) -> None:
        """键盘释放事件处理"""
        ...
```

### 4.7 Renderer 模块 (`renderer.py`)

```python
class Renderer:
    """Tkinter 渲染器"""

    SCALE: int              # 缩放倍数（默认 3，即 768×720）
    WIDTH: int = 256        # 原始宽度
    HEIGHT: int = 240       # 原始高度

    root: tk.Tk             # 主窗口
    canvas: tk.Canvas       # 渲染画布
    image: PhotoImage       # 当前帧图像
    emu: 'Emulator'         # 模拟器引用

    def __init__(self, emulator: 'Emulator', scale: int = 3):
        """
        初始化渲染窗口。

        Args:
            emulator: 模拟器实例，用于获取帧数据和输入事件
            scale: 画面缩放倍数
        """
        ...

    def render_frame(self, framebuffer: list[int]) -> None:
        """
        将帧缓冲区渲染到 Canvas。

        Args:
            framebuffer: 长度为 256*240 的列表，每个元素是 RGB 颜色值（0xRRGGBB）

        实现方式：
        - 将 framebuffer 转换为 Tkinter PhotoImage 格式
        - 在 Canvas 上显示图像
        """
        ...

    def bind_input(self, controller: Controller) -> None:
        """
        绑定键盘事件到控制器。

        Args:
            controller: 控制器实例
        """
        ...

    def mainloop(self) -> None:
        """启动 Tkinter 主循环"""
        ...
```

### 4.8 Emulator 主循环 (`emulator.py`)

```python
class Emulator:
    """FC 模拟器主控制器"""

    bus: Bus                # CPU 总线
    ppu_bus: PPUBus         # PPU 总线
    cpu: CPU6502            # CPU
    ppu: PPU                # PPU
    cartridge: Cartridge    # 卡带
    controller: Controller  # 输入
    renderer: Renderer      # 渲染器

    # NTSC 时钟参数
    CPU_CLOCK: int = 1789773        # CPU 主频
    PPU_CLOCK: int = CPU_CLOCK * 3  # PPU 主频（CPU 的 3 倍）
    FPS: int = 60                   # 目标帧率
    CYCLES_PER_FRAME: int = 29781   # 每帧 CPU 周期数

    running: bool           # 运行标志

    def __init__(self, rom_path: str, scale: int = 3):
        """
        初始化模拟器：加载 ROM，连接所有组件。

        Args:
            rom_path: .nes ROM 文件路径
            scale: 画面缩放倍数
        """
        ...

    def run(self) -> None:
        """启动模拟器，进入主循环"""
        ...

    def _run_frame(self) -> None:
        """
        执行一帧。

        流程：
        1. 循环执行 CPU 指令
        2. 每条指令后同步推进 PPU
        3. 当 PPU 完成一帧时停止
        4. 将帧缓冲区交给渲染器
        """
        ...

    def _tick(self, cpu_cycles: int) -> None:
        """
        同步 CPU 和 PPU 的时钟。

        Args:
            cpu_cycles: 本次 CPU 操作消耗的周期数
        关系：1 CPU 周期 = 3 PPU 周期
        """
        ...
```

### 4.9 调色板数据 (`palette.py`)

```python
# FC 系统调色板：64 色 → RGB 映射表
# 索引 0-63，每个对应一个 RGB 颜色值
PALETTE: list[int] = [
    0x666666, 0x002A88, 0x1412A7, 0x3B00A4,
    0x5C007E, 0x6E0040, 0x6C0600, 0x561D00,
    # ... 共 64 个颜色值
]

def get_color(palette_index: int) -> int:
    """根据调色板索引返回 RGB 颜色值"""
    return PALETTE[palette_index & 0x3F]
```

---

## 5. 项目文件结构

```
project/
├── doc/
│   └── requirements.md       # 本文档
├── src/
│   ├── __init__.py
│   ├── main.py               # 程序入口
│   ├── emulator.py           # 模拟器主控制器
│   ├── cpu.py                # 6502 CPU 模拟
│   ├── ppu.py                # PPU 图形处理
│   ├── bus.py                # CPU 总线
│   ├── ppu_bus.py            # PPU 总线
│   ├── cartridge.py          # ROM 加载 + Mapper
│   ├── input.py              # 输入处理
│   ├── renderer.py           # Tkinter 渲染器
│   └── palette.py            # 调色板数据
├── tests/                    # 测试目录（可选）
├── Super Mario Bros. (E) (PRG0) [!].nes  # ROM 文件
├── pyproject.toml
└── README.md
```

---

## 6. 开发里程碑

| 阶段 | 内容 | 验收标准 |
|------|------|----------|
| M1 | ROM 加载 + CPU 骨架 | 能加载 ROM，CPU 能执行 NOP、LDA 等基本指令 |
| M2 | 完整 CPU 指令集 | 通过 nestest.nes 测试 ROM（官方 6502 指令测试） |
| M3 | PPU 基础渲染 | 能显示背景画面（不含精灵和滚动） |
| M4 | 完整 PPU + 输入 | 能显示精灵，键盘可控制 |
| M5 | 超级玛丽可玩 | 能正常运行超级玛丽第一关 |

---

## 7. 风险和限制

| 风险 | 说明 | 缓解措施 |
|------|------|----------|
| Python 性能不足 | Python 解释执行 6502 指令较慢 | 扫描线级 PPU 精度；必要时用热点优化 |
| Tkinter 渲染性能 | PhotoImage 更新 256×240 可能卡顿 | 使用字符串批量构建像素数据 |
| 指令实现错误 | 6502 有 151 条指令 + 非官方指令 | 使用 nestest.nes 测试 ROM 验证 |
| PPU 时序复杂 | 超级玛丽依赖精灵 0 碰撞等细节 | 先实现基本版本，根据运行情况修复 |
