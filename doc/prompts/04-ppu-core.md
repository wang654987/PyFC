# Vibecoding Prompt 04: PPU 图形处理核心

## 概述

实现完整的 PPU（图形处理单元），包括寄存器读写、背景渲染、精灵渲染、滚动、VBlank/NMI 触发和精灵 0 碰撞检测。PPU 是模拟器中最复杂的模块。

## 前置条件

- `src/ppu_bus.py` 的 PPUBus 接口已定义（`read/write`）
- `src/palette.py` 的 `get_color` 函数可用
- PPU 通过 PPUBus 读取 CHR-ROM 和 Nametable

## 你要创建/修改的文件

### `src/ppu.py` — PPU 图形处理单元（约 600-800 行）

#### 1. PPU 类结构与寄存器

```python
from __future__ import annotations
from typing import TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    from .ppu_bus import PPUBus

class PPU:
    """NES PPU（图形处理单元）模拟器。

    使用扫描线级渲染精度。
    """

    # ---- 公开属性 ----
    framebuffer: list[int]           # 帧缓冲区 (256 × 240 个 RGB 值)
    frame_complete: bool             # 一帧是否渲染完成
    nmi_callback: Callable[[], None] | None  # NMI 回调（通知 CPU）
    scanline: int                    # 当前扫描线 (0-261)
    cycle: int                       # 当前扫描线内周期 (0-340)

    def __init__(self, ppu_bus: PPUBus) -> None:
        self.ppu_bus = ppu_bus

        # ---- PPU 寄存器（$2000-$2007）----
        self.ctrl: int = 0       # $2000 PPUCTRL
        self.mask: int = 0       # $2001 PPUMASK
        self.status: int = 0     # $2002 PPUSTATUS
        self.oam_addr: int = 0   # $2003 OAMADDR
        self.oam_data: int = 0   # $2004 OAMDATA
        self.scroll_x: int = 0   # $2005 首次写入
        self.scroll_y: int = 0   # $2005 二次写入
        self.vram_addr: int = 0  # $2006 当前 VRAM 地址
        self.read_buffer: int = 0  # $2007 预读缓冲区

        # ---- 内部锁存 ----
        self._write_latch: bool = False   # $2005/$2006 的双写锁存
        self._scroll_x: int = 0
        self._scroll_y: int = 0

        # ---- 内部存储 ----
        self.oam: bytearray = bytearray(256)     # 256 字节对象属性内存
        self.palette: bytearray = bytearray(32)   # 32 字节调色板 RAM
        self.framebuffer = [0] * (256 * 240)      # RGB 帧缓冲
        self.scanline = 0
        self.cycle = 0
        self.frame_complete = False
        self.nmi_callback = None
```

#### 2. PPU 寄存器定义详解

**$2000 PPUCTRL（只写）**：
```
Bit 0-1: Nametable 基地址
  00 = $2000, 01 = $2400, 10 = $2800, 11 = $2C00
Bit 2: VRAM 地址增量
  0 = 水平 +1, 1 = 垂直 +32
Bit 3: 精灵图案表地址
  0 = $0000, 1 = $1000
Bit 4: 背景图案表地址
  0 = $0000, 1 = $1000
Bit 5: 精灵大小
  0 = 8×8, 1 = 8×16
Bit 6: PPU 主/从选择（未使用）
Bit 7: NMI 使能（1 = 在 VBlank 期间生成 NMI）
```

**$2001 PPUMASK（只写）**：
```
Bit 0: 灰度模式
Bit 1: 显示背景最左 8 像素
Bit 2: 显示精灵最左 8 像素
Bit 3: 显示背景
Bit 4: 显示精灵
Bit 5: 强调红色
Bit 6: 强调绿色
Bit 7: 强调蓝色
```

**$2002 PPUSTATUS（只读）**：
```
Bit 0-4: 上次写入 $2006 的低 5 位（不常用）
Bit 5: 精灵溢出标志（每行超过 8 个精灵）
Bit 6: 精灵 0 碰撞标志
Bit 7: VBlank 标志（1 = 在 VBlank 期间）
```

#### 3. PPU 寄存器读写实现

```python
def cpu_read(self, address: int) -> int:
    """
    CPU 读取 PPU 寄存器（$2000-$2007）。

    读取 $2002 会清除 VBlank 标志和写入锁存。
    读取 $2007 使用预读缓冲区（调色板地址直接返回）。
    """
    reg = 0x2000 + (address & 0x07)

    if reg == 0x2002:  # PPUSTATUS
        result = self.status
        self.status &= 0x7F  # 清除 VBlank 标志（bit 7）
        self._write_latch = False
        return result | (result & 0x1F)  # 低 5 位包含上次总线值

    elif reg == 0x2004:  # OAMDATA
        return self.oam[self.oam_addr]

    elif reg == 0x2007:  # PPUDATA
        value = self.read_buffer
        self.read_buffer = self.ppu_bus.read(self.vram_addr & 0x3FFF)

        if (self.vram_addr & 0x3FFF) >= 0x3F00:
            # 调色板读取直接返回，预读缓冲区不变
            value = self.read_buffer
            self.read_buffer = self.ppu_bus.read(self.vram_addr & 0x3FFF)

        self.vram_addr += self._addr_increment()
        return value

    return 0

def cpu_write(self, address: int, value: int) -> None:
    """CPU 写入 PPU 寄存器。"""
    reg = 0x2000 + (address & 0x07)

    if reg == 0x2000:  # PPUCTRL
        self.ctrl = value

    elif reg == 0x2001:  # PPUMASK
        self.mask = value

    elif reg == 0x2003:  # OAMADDR
        self.oam_addr = value

    elif reg == 0x2004:  # OAMDATA
        self.oam[self.oam_addr] = value
        self.oam_addr = (self.oam_addr + 1) & 0xFF

    elif reg == 0x2005:  # PPUSCROLL
        if not self._write_latch:
            self._scroll_x = value
        else:
            self._scroll_y = value
        self._write_latch = not self._write_latch

    elif reg == 0x2006:  # PPUADDR
        if not self._write_latch:
            self.vram_addr = (self.vram_addr & 0x00FF) | ((value & 0x3F) << 8)
        else:
            self.vram_addr = (self.vram_addr & 0xFF00) | value
        self._write_latch = not self._write_latch

    elif reg == 0x2007:  # PPUDATA
        addr = self.vram_addr & 0x3FFF
        if addr >= 0x3F00:
            self._write_palette(addr, value)
        else:
            self.ppu_bus.write(addr, value)
        self.vram_addr += self._addr_increment()

def oam_write(self, index: int, value: int) -> None:
    """用于 OAM DMA 的 OAM 写入接口（由 Bus 调用）。"""
    self.oam[index & 0xFF] = value & 0xFF

def _addr_increment(self) -> int:
    """VRAM 地址增量：水平模式 +1，垂直模式 +32。"""
    return 32 if (self.ctrl & 0x04) else 1

def _write_palette(self, address: int, value: int) -> None:
    """
    写入调色板 RAM。
    $3F10/$3F14/$3F18/$3F1C 镜像到 $3F00/$3F04/$3F08/$3F0C（通用背景色）。
    """
    addr = address & 0x1F
    if addr in (0x10, 0x14, 0x18, 0x1C):
        addr -= 0x10
    self.palette[addr] = value & 0x3F
```

#### 4. tick() 方法与 VBlank 处理

```python
def tick(self) -> None:
    """
    推进一个 PPU 周期（3 PPU 周期 = 1 CPU 周期）。

    scanline 0-239: 可见区域
    scanline 240:    空闲
    scanline 241:    VBlank 设置
    scanline 242-260: VBlank 持续
    scanline 261:    预渲染

    在扫描线级精度下，只有关键时间点需要处理：
    - 每条扫描线的 cycle 0-255: 渲染像素（仅在可见行）
    - scanline 241, cycle 1: 设置 VBlank 标志 + 可能的 NMI
    - scanline 261, cycle 1: 清除 VBlank / 精灵 0 碰撞
    """
    # 可见扫描线：渲染
    if self.scanline < 240 and self.cycle < 256:
        self._render_pixel(self.cycle, self.scanline)

    self.cycle += 1
    if self.cycle > 340:
        self.cycle = 0
        self.scanline += 1

        if self.scanline == 241:
            self._set_vblank()
        elif self.scanline > 261:
            self.scanline = 0
            self.frame_complete = True

def _set_vblank(self) -> None:
    """设置 VBlank 标志并触发 NMI（如果使能）。"""
    self.status |= 0x80           # 设置 VBlank 标志
    if self.ctrl & 0x80:          # NMI 使能检查
        if self.nmi_callback:
            self.nmi_callback()

def reset(self) -> None:
    """复位 PPU。"""
    self.ctrl = 0
    self.mask = 0
    self.status = 0
    self.oam_addr = 0
    self.scanline = 0
    self.cycle = 0
    self.frame_complete = False
    self._write_latch = False
    self.oam = bytearray(256)
    self.palette = bytearray(32)
```

#### 5. 背景渲染详细流程

```python
def _render_pixel(self, x: int, y: int) -> None:
    """渲染 (x, y) 位置的单个像素。"""
    bg_color = self._get_background_pixel(x, y)
    spr_color, spr_priority, spr_zero = self._get_sprite_pixel(x, y)

    # 优先级合成
    if spr_color != 0:
        if spr_priority == 0 or bg_color == 0:
            final = spr_color
        else:
            final = bg_color
    else:
        final = bg_color

    # 精灵 0 碰撞检测
    if spr_zero and bg_color != 0 and spr_color != 0:
        if x < 255:  # 不在最右侧
            self.status |= 0x40

    self.framebuffer[y * 256 + x] = final

def _get_background_pixel(self, x: int, y: int) -> int:
    """
    获取背景层 (x, y) 处的颜色（返回 0xRRGGBB）。

    流程：
    1. 应用滚动偏移
    2. 计算 Nametable 中的 Tile 坐标
    3. 从 Nametable 读取 Tile 编号
    4. 从 Attribute Table 读取调色板组
    5. 从 CHR-ROM 读取 Tile 位图数据
    6. 合成 2-bit 颜色索引
    7. 查调色板获取 RGB 颜色
    """
    if not (self.mask & 0x08):  # 背景显示关闭
        return 0

    # 1. 应用滚动
    scrolled_x = (x + self._scroll_x) % 512
    scrolled_y = (y + self._scroll_y) % 480

    # 2. 确定 Nametable 基地址
    nt_base = 0x2000
    if scrolled_x >= 256:
        nt_base ^= 0x0400
    if scrolled_y >= 240:
        nt_base ^= 0x0800

    tile_x = (scrolled_x % 256) // 8
    tile_y = (scrolled_y % 240) // 8
    fine_x = scrolled_x % 8
    fine_y = scrolled_y % 8

    # 3. 读取 Tile 编号
    tile_addr = nt_base + tile_y * 32 + tile_x
    tile_index = self.ppu_bus.read(tile_addr)

    # 4. 读取 Attribute Table
    attr_addr = 0x23C0 | (nt_base & 0x0C00) | ((tile_y // 4) * 8) | (tile_x // 4)
    attr_byte = self.ppu_bus.read(attr_addr)
    shift = ((tile_y & 2) << 1) | ((tile_x & 2) << 0)
    palette_group = (attr_byte >> shift) & 0x03

    # 5. 读取 Tile 位图数据
    pattern_base = 0x1000 if (self.ctrl & 0x10) else 0x0000
    pattern_addr = pattern_base + tile_index * 16 + fine_y
    low_byte = self.ppu_bus.read(pattern_addr)
    high_byte = self.ppu_bus.read(pattern_addr + 8)

    # 6. 合成 2-bit 颜色索引
    bit_pos = 7 - fine_x
    low_bit = (low_byte >> bit_pos) & 1
    high_bit = (high_byte >> bit_pos) & 1
    color_index = (high_bit << 1) | low_bit

    if color_index == 0:
        return self._read_palette(0)  # 通用背景色

    # 7. 查调色板
    palette_addr = 0x3F00 + palette_group * 4 + color_index
    color = self._read_palette(palette_addr)
    from .palette import get_color
    return get_color(color)
```

#### 6. 精灵渲染

```python
def _get_sprite_pixel(self, x: int, y: int) -> tuple[int, int, bool]:
    """
    获取精灵层 (x, y) 处的颜色。

    Returns:
        (color, priority, is_sprite_zero)

    精灵优先级规则：
    - OAM 索引越小优先级越高
    - 先渲染高优先级精灵（索引大），后渲染低优先级（索引小）
    - 如果精灵在背景后（priority=1），只在不透明背景上渲染
    """
    if not (self.mask & 0x10):  # 精灵显示关闭
        return (0, 0, False)

    sprite_height = 16 if (self.ctrl & 0x20) else 8
    pattern_base_spr = 0x1000 if (self.ctrl & 0x08) else 0x0000

    is_sprite_zero = False

    # 遍历 OAM（反向：低索引覆盖高索引）
    for i in range(63, -1, -1):
        spr_y = self.oam[i * 4] + 1
        tile_index = self.oam[i * 4 + 1]
        attr = self.oam[i * 4 + 2]
        spr_x = self.oam[i * 4 + 3]

        if x < spr_x or x >= spr_x + 8:
            continue
        sprite_y_offset = y - spr_y
        if sprite_y_offset < 0 or sprite_y_offset >= sprite_height:
            continue

        # 处理翻转
        flip_v = (attr >> 7) & 1
        flip_h = (attr >> 6) & 1
        palette_group = attr & 0x03
        priority = (attr >> 5) & 1

        tile_row = sprite_y_offset
        if flip_v:
            tile_row = sprite_height - 1 - tile_row

        pixel_col = x - spr_x
        if flip_h:
            pixel_col = 7 - pixel_col

        # 读取精灵图案数据
        if sprite_height == 8:
            pattern_addr = pattern_base_spr + tile_index * 16 + tile_row
        else:
            # 8x16 模式
            bank = tile_index & 1
            base_tile = tile_index & 0xFE
            if tile_row >= 8:
                pattern_addr = 0x1000 * bank + (base_tile + 1) * 16 + (tile_row - 8)
            else:
                pattern_addr = 0x1000 * bank + base_tile * 16 + tile_row

        low_byte = self.ppu_bus.read(pattern_addr)
        high_byte = self.ppu_bus.read(pattern_addr + 8)

        bit_pos = 7 - pixel_col
        low_bit = (low_byte >> bit_pos) & 1
        high_bit = (high_byte >> bit_pos) & 1
        color_index = (high_bit << 1) | low_bit

        if color_index == 0:
            continue  # 透明像素

        palette_addr = 0x3F10 + palette_group * 4 + color_index
        color = self._read_palette(palette_addr)
        from .palette import get_color

        if i == 0:
            is_sprite_zero = True

        return (get_color(color), priority, is_sprite_zero)

    return (0, 0, False)

def _read_palette(self, address: int) -> int:
    """读取调色板（处理镜像）。"""
    addr = address & 0x1F
    if addr in (0x10, 0x14, 0x18, 0x1C):
        addr -= 0x10
    return self.palette[addr]
```

#### 7. PPU 状态控制

在 tick() 中，除了 VBlank 处理外，还需处理：

- **扫描线 261（预渲染）**：清除 VBlank 标志，清除精灵 0 碰撞标志，清除精灵溢出标志
- **frame_complete 标志**：当扫描线从 261 变为 0 时设置

```python
# tick() 方法中扫描线切换部分的补充：
if self.scanline == 261:
    self.status &= 0x1F  # 清除 VBlank (bit7)、精灵0碰撞(bit6)、精灵溢出(bit5)
    self.frame_complete = True
elif self.scanline > 261:
    self.scanline = 0
```

## 测试要求

### `tests/test_ppu.py`

使用 Mock PPUBus：

```python
class MockPPUBus:
    def __init__(self):
        self.memory: dict[int, int] = {}
    def read(self, address: int) -> int:
        return self.memory.get(address & 0x3FFF, 0)
    def write(self, address: int, value: int) -> None:
        self.memory[address & 0x3FFF] = value & 0xFF
```

至少包含以下测试（按类别）：

**寄存器测试**：
1. `test_ppuctrl_write` — 写入 $2000，验证 ctrl 更新
2. `test_ppumask_write` — 写入 $2001，验证 mask 更新
3. `test_ppustatus_read_clears_vblank` — 读 $2002 清除 bit 7
4. `test_ppustatus_read_resets_latch` — 读 $2002 重置写入锁存
5. `test_ppuscroll_first_write` — 首次写入 $2005 存为 X 滚动
6. `test_ppuscroll_second_write` — 二次写入 $2005 存为 Y 滚动
7. `test_ppuaddr_two_writes` — 两次写入 $2006 构造 16 位地址
8. `test_ppudata_read_buffer` — 读 $2007 使用预读缓冲
9. `test_ppudata_write_palette_mirror` — 写 $3F10 镜像到 $3F00

**VBlank/NMI 测试**：
10. `test_vblank_set_on_scanline_241` — 进入扫描线 241 时 VBlank 标志置位
11. `test_nmi_callback_called` — NMI 使能时回调被调用（使用 Mock 回调计数）
12. `test_nmi_not_called_when_disabled` — NMI 禁用时不调用回调
13. `test_vblank_cleared_on_prerender` — 扫描线 261 清除 VBlank

**背景渲染测试**：
14. `test_background_pixel_with_known_tile` — 预设 Nametable/CHR-ROM，验证像素值
15. `test_background_disabled_returns_zero` — 背景关闭时像素为 0
16. `test_scroll_affects_background` — 滚动偏移影响背景像素位置
17. `test_attribute_table_palette_group` — 验证属性表影响调色板组

**精灵渲染测试**：
18. `test_sprite_pixel_visible` — 预设 OAM，验证精灵像素可见
19. `test_sprite_priority` — 低优先级精灵在背景后
20. `test_sprite_horizontal_flip` — 水平翻转精灵
21. `test_sprite_vertical_flip` — 垂直翻转精灵
22. `test_sprite_zero_collision` — 精灵 0 与背景重叠时设置碰撞标志
23. `test_sprite_8x16_mode` — 8×16 精灵模式
24. `test_sprite_transparent_pixels` — 透明像素不绘制

**帧缓冲区测试**：
25. `test_framebuffer_initialized` — 帧缓冲区初始化为 256×240
26. `test_frame_complete_flag` — 完成一帧后 frame_complete 为 True

## 质量检查

```bash
# 1. ruff 代码风格检查
ruff check src/ppu.py tests/test_ppu.py

# 2. mypy 类型检查
mypy src/ppu.py

# 3. pytest 单元测试
pytest tests/test_ppu.py -v
```

## 文件清单

```
src/ppu.py                # ← 创建
tests/test_ppu.py         # ← 创建
```

## 与其他模块的接口

| 被依赖模块 | 使用方式 |
|-----------|---------|
| `bus.py` | 调用 `ppu.cpu_read(addr)` / `ppu.cpu_write(addr, val)` / `ppu.oam_write(i, val)` |
| `emulator.py` | 创建 PPU 实例，设置 `nmi_callback`，在帧循环中调用 `tick()`，读取 `framebuffer` 和 `frame_complete` |
| `renderer.py` | 读取 `ppu.framebuffer` 渲染画面 |

## 验收标准

- [ ] 所有 8 个 PPU 寄存器正确实现（含两次写入锁存）
- [ ] 背景层渲染正确（Nametable + Attribute Table + CHR-ROM）
- [ ] 精灵层渲染正确（OAM + 翻转 + 8×16 模式）
- [ ] 精灵 0 碰撞检测正确
- [ ] 滚动功能正确
- [ ] VBlank 标志在正确时间设置/清除
- [ ] NMI 回调在 NMI 使能时正确触发
- [ ] 所有 pytest 测试通过（26+）
- [ ] mypy 类型检查无错误
- [ ] ruff 代码风格检查无错误
