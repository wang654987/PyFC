# M3: PPU 基础渲染

> 目标：实现 PPU 基础渲染，能显示超级玛丽背景画面
> 验收标准：能正确显示游戏背景，无精灵

---

## 任务清单

### 3.1 PPU 模块骨架（ppu.py）

**目标**：创建 PPU 类基础结构

- [ ] 定义 PPU 类
- [ ] 定义 PPU 寄存器属性
- [ ] 定义内部状态（OAM, VRAM, Palette）
- [ ] 定义帧缓冲区（256×240）
- [ ] 实现 reset() 方法
- [ ] 实现 tick() 方法骨架

**PPU 寄存器**：
```python
class PPU:
    def __init__(self, ppu_bus):
        # PPU 寄存器
        self.ctrl = 0       # $2000 PPUCTRL
        self.mask = 0       # $2001 PPUMASK
        self.status = 0     # $2002 PPUSTATUS
        self.oam_addr = 0   # $2003 OAMADDR
        self.oam_data = 0   # $2004 OAMDATA
        self.scroll_x = 0   # $2005 PPUSCROLL (X)
        self.scroll_y = 0   # $2005 PPUSCROLL (Y)
        self.addr = 0       # $2006 PPUADDR
        self.data_buffer = 0 # $2007 读取缓冲
        
        # 内部状态
        self.oam = bytearray(256)
        self.vram = bytearray(2048)
        self.palette = bytearray(32)
        self.framebuffer = [0] * (256 * 240)
        
        # 渲染状态
        self.scanline = 0
        self.cycle = 0
        self.frame_complete = False
        self.addr_latch = False
        self.scroll_latch = False
```

**VideCoding 检查点**：
```python
ppu = PPU(ppu_bus)
ppu.reset()
assert ppu.scanline == 0
assert ppu.cycle == 0
assert len(ppu.framebuffer) == 256 * 240
```

---

### 3.2 PPU 总线模块（ppu_bus.py）

**目标**：实现 PPU 地址空间映射

- [ ] 定义 PPUBus 类
- [ ] 初始化 Nametable RAM（2KB）
- [ ] 实现地址解码逻辑
- [ ] 实现 read() 方法
- [ ] 实现 write() 方法
- [ ] 实现 Nametable 镜像逻辑

**PPU 地址空间**：
```
$0000-$0FFF: Pattern Table 0 (CHR-ROM)
$1000-$1FFF: Pattern Table 1 (CHR-ROM)
$2000-$23FF: Nametable 0
$2400-$27FF: Nametable 1
$2800-$2BFF: Nametable 2 (镜像)
$2C00-$2FFF: Nametable 3 (镜像)
$3F00-$3F1F: Palette RAM
```

**Nametable 镜像实现**：
```python
def _mirror_nametable(self, address: int) -> int:
    address = (address - 0x2000) % 0x1000
    if self.mirror_mode == 0:  # 水平镜像
        if address >= 0x0800:
            address -= 0x0400
    else:  # 垂直镜像
        if address >= 0x0800:
            address -= 0x0800
    return address
```

**VideCoding 检查点**：
```python
ppu_bus = PPUBus(cartridge)
ppu_bus.write(0x2000, 0x42)
assert ppu_bus.read(0x2000) == 0x42
assert ppu_bus.read(0x2400) == 0x42  # 水平镜像
```

---

### 3.3 PPU 寄存器实现

**目标**：实现 CPU 对 PPU 寄存器的读写

- [ ] 实现 $2000 PPUCTRL 写入
- [ ] 实现 $2001 PPUMASK 写入
- [ ] 实现 $2002 PPUSTATUS 读取
- [ ] 实现 $2003 OAMADDR 写入
- [ ] 实现 $2004 OAMDATA 读写
- [ ] 实现 $2005 PPUSCROLL 写入（两次）
- [ ] 实现 $2006 PPUADDR 写入（两次）
- [ ] 实现 $2007 PPUDATA 读写

**PPUCTRL 位定义**：
```
Bit 0-1: Nametable 地址
  00 = $2000, 01 = $2400, 10 = $2800, 11 = $2C00
Bit 2: VRAM 地址递增
  0 = +1 (横向), 1 = +32 (纵向)
Bit 3: Sprite Pattern Table
  0 = $0000, 1 = $1000
Bit 4: Background Pattern Table
  0 = $0000, 1 = $1000
Bit 5: Sprite Size
  0 = 8x8, 1 = 8x16
Bit 7: NMI 使能
```

**cpu_read/cpu_write 实现**：
```python
def cpu_read(self, address: int) -> int:
    address = 0x2000 + (address & 0x07)
    
    if address == 0x2002:  # PPUSTATUS
        value = self.status
        self.status &= 0x7F  # 清除 VBlank
        self.addr_latch = False
        self.scroll_latch = False
        return value
    elif address == 0x2004:  # OAMDATA
        return self.oam[self.oam_addr]
    elif address == 0x2007:  # PPUDATA
        value = self.data_buffer
        self.data_buffer = self.ppu_bus.read(self.addr)
        if self.addr >= 0x3F00:
            value = self.palette[self.addr & 0x1F]
        self.addr += 32 if (self.ctrl & 0x04) else 1
        return value
    return 0

def cpu_write(self, address: int, value: int):
    address = 0x2000 + (address & 0x07)
    
    if address == 0x2000:  # PPUCTRL
        self.ctrl = value
    elif address == 0x2001:  # PPUMASK
        self.mask = value
    elif address == 0x2005:  # PPUSCROLL
        if not self.scroll_latch:
            self.scroll_x = value
        else:
            self.scroll_y = value
        self.scroll_latch = not self.scroll_latch
    elif address == 0x2006:  # PPUADDR
        if not self.addr_latch:
            self.addr = (self.addr & 0x00FF) | (value << 8)
        else:
            self.addr = (self.addr & 0xFF00) | value
        self.addr_latch = not self.addr_latch
    elif address == 0x2007:  # PPUDATA
        self.ppu_bus.write(self.addr, value)
        self.addr += 32 if (self.ctrl & 0x04) else 1
```

**VideCoding 检查点**：
```python
# 测试 PPUCTRL 写入
ppu.cpu_write(0x2000, 0x80)  # 启用 NMI
assert ppu.ctrl == 0x80

# 测试 PPUSTATUS 读取
ppu.status = 0x80  # VBlank
value = ppu.cpu_read(0x2002)
assert value == 0x80
assert ppu.status == 0x00  # VBlank 已清除
```

---

### 3.4 调色板数据（palette.py）

**目标**：实现 FC 系统调色板

- [ ] 定义 64 色 RGB 映射表
- [ ] 实现 get_color() 函数
- [ ] 支持调色板索引查询

**调色板数据**：
```python
PALETTE = [
    0x666666, 0x002A88, 0x1412A7, 0x3B00A4,
    0x5C007E, 0x6E0040, 0x6C0600, 0x561D00,
    0x333400, 0x0B4800, 0x005200, 0x004F08,
    0x00404D, 0x000000, 0x000000, 0x000000,
    0xADADAD, 0x155FD9, 0x4240FF, 0x7527FE,
    0xA01ACC, 0xB71E7B, 0xB53120, 0x994E00,
    0x6B6D00, 0x388700, 0x0C9300, 0x008F32,
    0x007C8D, 0x000000, 0x000000, 0x000000,
    # ... 共 64 个颜色
]

def get_color(index: int) -> int:
    return PALETTE[index & 0x3F]
```

**VideCoding 检查点**：
```python
from palette import get_color
assert get_color(0) == 0x666666
assert get_color(0x3F) == 0x000000
```

---

### 3.5 背景渲染

**目标**：实现背景层渲染

- [ ] 实现 Tile 数据读取（Pattern Table）
- [ ] 实现 Nametable 读取
- [ ] 实现 Attribute Table 读取
- [ ] 实现背景像素颜色计算
- [ ] 实现 _render_scanline() 方法
- [ ] 实现 _get_background_pixel() 方法

**Tile 数据结构**：
```
每个 Tile 8x8 像素，2 位色深
- 低字节平面：$0000-$0FFF (Pattern Table 0)
- 高字节平面：$1000-$1FFF (Pattern Table 1)

像素颜色 = (高字节位 << 1) | 低字节位
```

**背景渲染流程**：
```python
def _render_background(self):
    pattern_base = 0x1000 if (self.ctrl & 0x10) else 0x0000
    
    for pixel_x in range(256):
        # 计算 Nametable 坐标
        nt_x = (pixel_x + self.scroll_x) % 512
        nt_y = (self.scanline + self.scroll_y) % 240
        
        # 获取 Tile 编号
        nt_addr = 0x2000 + (nt_y // 8) * 32 + (nt_x // 8)
        tile_id = self.ppu_bus.read(nt_addr)
        
        # 获取 Tile 像素
        tile_x = nt_x % 8
        tile_y = nt_y % 8
        pattern_addr = pattern_base + tile_id * 16 + tile_y
        
        low_bit = (self.ppu_bus.read(pattern_addr) >> (7 - tile_x)) & 1
        high_bit = (self.ppu_bus.read(pattern_addr + 8) >> (7 - tile_x)) & 1
        color_index = (high_bit << 1) | low_bit
        
        # 获取调色板
        attr_addr = 0x23C0 + (nt_y // 32) * 8 + (nt_x // 32)
        attr_byte = self.ppu_bus.read(attr_addr)
        palette_index = (attr_byte >> ((nt_y % 32 // 16) * 4 + (nt_x % 32 // 16) * 2)) & 0x03
        
        # 最终颜色
        palette_addr = 0x3F00 + palette_index * 4 + color_index
        color = self.ppu_bus.read(palette_addr)
        
        self.framebuffer[self.scanline * 256 + pixel_x] = get_color(color)
```

**VideCoding 检查点**：
```python
# 渲染一帧后检查
ppu.scanline = 100
ppu._render_scanline()
# 检查 framebuffer 有非零值
assert any(ppu.framebuffer[100*256:101*256])
```

---

### 3.6 基础渲染器（renderer.py）

**目标**：实现 Tkinter 渲染窗口

- [ ] 定义 Renderer 类
- [ ] 创建 Tkinter 窗口
- [ ] 创建 Canvas 组件
- [ ] 实现 render_frame() 方法
- [ ] 实现帧缓冲区到 PhotoImage 转换
- [ ] 实现 mainloop() 方法

**渲染器实现**：
```python
import tkinter as tk

class Renderer:
    def __init__(self, emulator, scale=3):
        self.scale = scale
        self.root = tk.Tk()
        self.root.title("PyFC - FC Emulator")
        
        self.canvas = tk.Canvas(
            self.root,
            width=256 * scale,
            height=240 * scale
        )
        self.canvas.pack()
        
        self.image = None
    
    def render_frame(self, framebuffer):
        # 创建 PhotoImage
        self.image = tk.PhotoImage(width=256, height=240)
        
        for y in range(240):
            for x in range(256):
                color = framebuffer[y * 256 + x]
                r = (color >> 16) & 0xFF
                g = (color >> 8) & 0xFF
                b = color & 0xFF
                self.image.put(f'#{r:02x}{g:02x}{b:02x}', (x, y))
        
        # 缩放显示
        if self.scale > 1:
            self.image = self.image.zoom(self.scale, self.scale)
        
        self.canvas.create_image(0, 0, image=self.image, anchor='nw')
        self.root.update()
```

**VideCoding 检查点**：
```python
renderer = Renderer(emulator, scale=2)
renderer.render_frame([0x666666] * (256 * 240))
# 应该显示灰色窗口
```

---

### 3.7 整合测试

**目标**：显示超级玛丽背景画面

- [ ] 连接所有模块
- [ ] 实现基本帧循环
- [ ] 加载超级玛丽 ROM
- [ ] 渲染第一帧背景
- [ ] 验证画面正确性

**测试代码**：
```python
from cartridge import Cartridge
from bus import Bus
from ppu_bus import PPUBus
from ppu import PPU
from cpu import CPU6502
from renderer import Renderer

# 初始化
cart = Cartridge("Super Mario Bros. (E) (PRG0) [!].nes")
bus = Bus()
ppu_bus = PPUBus(cart)
ppu = PPU(ppu_bus)
cpu = CPU6502(bus)
renderer = Renderer(None, scale=2)

# 连接组件
bus.ppu = ppu
bus.cartridge = cart
ppu.ppu_bus = ppu_bus

# 运行几帧
for _ in range(3):
    while not ppu.frame_complete:
        cpu.step()
    renderer.render_frame(ppu.framebuffer)
    ppu.frame_complete = False
```

---

## M3 完成标准

- [ ] PPU 能正确读写寄存器
- [ ] 能读取 CHR-ROM 数据
- [ ] 能渲染背景 Tile
- [ ] 能正确处理调色板
- [ ] 能显示超级玛丽背景画面
- [ ] 无崩溃，无明显渲染错误
