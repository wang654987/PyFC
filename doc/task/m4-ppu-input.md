# M4: 完整 PPU + 输入

> 目标：实现完整 PPU 渲染和输入处理
> 验收标准：能显示精灵，键盘可控制游戏

---

## 任务清单

### 4.1 精灵渲染（OAM + Sprites）

**目标**：实现精灵层渲染

- [ ] 实现 OAM 数据结构
- [ ] 实现精灵属性解析（Y, Tile, Attr, X）
- [ ] 实现精灵优先级处理
- [ ] 实现精灵调色板
- [ ] 实现精灵水平/垂直翻转
- [ ] 实现精灵 8x8 和 8x16 模式
- [ ] 实现 _get_sprite_pixel() 方法
- [ ] 实现 _evaluate_sprites() 方法

**精灵属性结构**：
```
每个精灵 4 字节：
Byte 0: Y 坐标（实际 Y = Byte0 + 1）
Byte 1: Tile 编号
Byte 2: 属性
  Bit 0-1: 调色板（4 组精灵调色板）
  Bit 5: 优先级（0=在背景前，1=在背景后）
  Bit 6: 水平翻转
  Bit 7: 垂直翻转
Byte 3: X 坐标
```

**精灵渲染实现**：
```python
def _render_sprites(self):
    pattern_base = 0x1000 if (self.ctrl & 0x08) else 0x0000
    sprite_size = 16 if (self.ctrl & 0x20) else 8
    
    # 获取当前扫描线的精灵
    sprites_on_line = []
    for i in range(64):
        y = self.oam[i * 4] + 1
        if y <= self.scanline < y + sprite_size:
            if len(sprites_on_line) < 8:
                sprites_on_line.append(i)
            else:
                self.status |= 0x20  # 精灵溢出
                break
    
    # 渲染精灵（反向优先级）
    for i in reversed(sprites_on_line):
        y = self.oam[i * 4] + 1
        tile = self.oam[i * 4 + 1]
        attr = self.oam[i * 4 + 2]
        x = self.oam[i * 4 + 3]
        
        # 获取精灵调色板
        palette_index = attr & 0x03
        priority = (attr >> 5) & 0x01
        flip_h = (attr >> 6) & 0x01
        flip_v = (attr >> 7) & 0x01
        
        # 渲染精灵像素
        tile_y = self.scanline - y
        if flip_v:
            tile_y = sprite_size - 1 - tile_y
        
        for tile_x in range(8):
            pixel_x = x + tile_x
            if pixel_x >= 256:
                continue
            
            if flip_h:
                tx = 7 - tile_x
            else:
                tx = tile_x
            
            # 读取 Tile 数据
            if sprite_size == 8:
                pattern_addr = pattern_base + tile * 16 + tile_y
            else:
                # 8x16 模式
                if tile_y < 8:
                    pattern_addr = (tile & 0xFE) * 16 + tile_y
                else:
                    pattern_addr = ((tile & 0xFE) + 1) * 16 + (tile_y - 8)
            
            low_bit = (self.ppu_bus.read(pattern_addr) >> (7 - tx)) & 1
            high_bit = (self.ppu_bus.read(pattern_addr + 8) >> (7 - tx)) & 1
            color_index = (high_bit << 1) | low_bit
            
            if color_index == 0:  # 透明
                continue
            
            # 获取颜色
            palette_addr = 0x3F10 + palette_index * 4 + color_index
            color = self.ppu_bus.read(palette_addr)
            
            # 精灵 0 碰撞检测
            if i == 0 and color_index != 0:
                # 检查是否与背景重叠
                bg_pixel = self.framebuffer[self.scanline * 256 + pixel_x]
                if bg_pixel != 0:
                    self.status |= 0x40  # 精灵 0 碰撞
            
            # 绘制像素（考虑优先级）
            if priority == 0:  # 在背景前
                self.framebuffer[self.scanline * 256 + pixel_x] = get_color(color)
            else:  # 在背景后
                bg_pixel = self.framebuffer[self.scanline * 256 + pixel_x]
                if bg_pixel == 0:
                    self.framebuffer[self.scanline * 256 + pixel_x] = get_color(color)
```

**VideCoding 检查点**：
```python
# 写入测试精灵
ppu.oam[0] = 100   # Y
ppu.oam[1] = 0x00  # Tile
ppu.oam[2] = 0x00  # 属性
ppu.oam[3] = 50    # X

ppu.scanline = 100
ppu._render_scanline()
# 检查精灵位置有像素
assert ppu.framebuffer[100 * 256 + 50] != 0
```

---

### 4.2 滚动（Scroll）实现

**目标**：实现 PPU 滚动功能

- [ ] 实现水平滚动
- [ ] 实现垂直滚动
- [ ] 实现滚动寄存器（$2005 两次写入）
- [ ] 实现精细滚动（Fine Scroll）
- [ ] 实现 Nametable 切换

**滚动实现**：
```python
def _get_nametable_address(self, pixel_x: int, pixel_y: int) -> int:
    """根据滚动获取 Nametable 地址"""
    # 应用滚动偏移
    x = (pixel_x + self.scroll_x) % 512
    y = (pixel_y + self.scroll_y) % 240
    
    # 计算 Nametable 索引
    nt_index = 0
    if x >= 256:
        nt_index ^= 0x0400
        x -= 256
    if y >= 240:
        nt_index ^= 0x0800
        y -= 240
    
    # 计算 Tile 坐标
    tile_x = x // 8
    tile_y = y // 8
    
    return 0x2000 + nt_index + tile_y * 32 + tile_x
```

**VideCoding 检查点**：
```python
# 测试滚动
ppu.scroll_x = 16
ppu.scroll_y = 0
# 渲染后检查画面偏移
```

---

### 4.3 输入模块（input.py）

**目标**：实现手柄控制器模拟

- [ ] 定义 Controller 类
- [ ] 定义按钮常量
- [ ] 定义键位映射表
- [ ] 实现 write() 方法（锁存）
- [ ] 实现 read() 方法（串行读取）
- [ ] 实现 key_press() 方法
- [ ] 实现 key_release() 方法

**键位映射**：
```python
KEY_MAP = {
    'w': BUTTON_UP,
    's': BUTTON_DOWN,
    'a': BUTTON_LEFT,
    'd': BUTTON_RIGHT,
    'j': BUTTON_A,
    'k': BUTTON_B,
    'Return': BUTTON_START,
    'Shift_R': BUTTON_SELECT,
    'Up': BUTTON_UP,
    'Down': BUTTON_DOWN,
    'Left': BUTTON_LEFT,
    'Right': BUTTON_RIGHT,
    'z': BUTTON_A,
    'x': BUTTON_B,
}
```

**手柄协议实现**：
```python
class Controller:
    def __init__(self):
        self.button_state = 0
        self.strobe = False
        self.shift_register = 0
    
    def write(self, value: int):
        self.strobe = value & 0x01
        if self.strobe:
            self.shift_register = self.button_state
    
    def read(self) -> int:
        if self.strobe:
            return self.button_state & 0x01
        
        value = self.shift_register & 0x01
        self.shift_register >>= 1
        return value
    
    def key_press(self, key: str):
        if key in KEY_MAP:
            self.button_state |= (1 << KEY_MAP[key])
    
    def key_release(self, key: str):
        if key in KEY_MAP:
            self.button_state &= ~(1 << KEY_MAP[key])
```

**VideCoding 检查点**：
```python
ctrl = Controller()
ctrl.key_press('w')
ctrl.write(1)  # 锁存
ctrl.write(0)  # 开始读取
assert ctrl.read() == 0  # A 按钮未按下
assert ctrl.read() == 1  # 上方向按下
```

---

### 4.4 键盘事件处理

**目标**：实现键盘事件捕获和处理

- [ ] 在 Renderer 中绑定键盘事件
- [ ] 实现 KeyPress 事件处理
- [ ] 实现 KeyRelease 事件处理
- [ ] 连接键盘事件到 Controller

**事件绑定**：
```python
class Renderer:
    def bind_input(self, controller):
        self.root.bind('<KeyPress>', lambda e: controller.key_press(e.keysym))
        self.root.bind('<KeyRelease>', lambda e: controller.key_release(e.keysym))
        self.root.focus_set()
```

**VideCoding 检查点**：
```python
# 按下 W 键后检查控制器状态
renderer.bind_input(controller)
# 模拟键盘事件
controller.key_press('w')
assert controller.button_state & (1 << BUTTON_UP)
```

---

### 4.5 精灵 0 碰撞检测

**目标**：实现精灵 0 与背景的碰撞检测

- [ ] 实现精灵 0 碰撞检测逻辑
- [ ] 设置 PPUSTATUS 标志（Bit 6）
- [ ] 在渲染扫描线时检测

**碰撞检测逻辑**：
```python
# 在渲染精灵时检测
if sprite_index == 0:
    # 检查精灵像素是否与背景像素重叠
    bg_color = self.framebuffer[self.scanline * 256 + pixel_x]
    if bg_color != 0 and color_index != 0:
        self.status |= 0x40  # 设置精灵 0 碰撞标志
```

**VideCoding 检查点**：
```python
# 精灵 0 与背景重叠时设置标志
ppu.status = 0
ppu._render_scanline()
# 如果精灵 0 与背景重叠
assert ppu.status & 0x40
```

---

### 4.6 VBlank 与 NMI 触发

**目标**：正确处理 VBlank 和 NMI

- [ ] 在扫描线 241 设置 VBlank 标志
- [ ] 如果 NMI 使能，触发 CPU NMI
- [ ] 在扫描线 261 重置 VBlank
- [ ] 实现帧完成标志

**VBlank 处理**：
```python
def tick(self):
    self.cycle += 1
    
    if self.cycle >= 341:
        self.cycle = 0
        self.scanline += 1
        
        if self.scanline == 241:  # VBlank 开始
            self.status |= 0x80
            self.frame_complete = True
            if self.ctrl & 0x80:  # NMI 使能
                self.nmi_callback()
        
        elif self.scanline == 261:  # 预渲染行
            self.status &= 0x7F  # 清除 VBlank
            self.scanline = 0
```

**VideCoding 检查点**：
```python
# VBlank 期间检查标志
ppu.scanline = 241
ppu.cycle = 1
ppu.tick()
assert ppu.status & 0x80  # VBlank 标志设置
```

---

### 4.7 整合测试

**目标**：实现完整的游戏画面和输入

- [ ] 连接所有模块
- [ ] 实现完整帧循环
- [ ] 渲染背景和精灵
- [ ] 响应键盘输入
- [ ] 验证游戏可玩性

**测试代码**：
```python
# 完整初始化
cart = Cartridge("Super Mario Bros. (E) (PRG0) [!].nes")
bus = Bus()
ppu_bus = PPUBus(cart)
ppu = PPU(ppu_bus)
cpu = CPU6502(bus)
controller = Controller()
renderer = Renderer(None, scale=2)

# 连接组件
bus.ppu = ppu
bus.cartridge = cart
bus.controller = controller
ppu.ppu_bus = ppu_bus

# 绑定输入
renderer.bind_input(controller)

# 主循环
def run_frame():
    ppu.frame_complete = False
    while not ppu.frame_complete:
        cycles = cpu.step()
        for _ in range(cycles * 3):
            ppu.tick()
    renderer.render_frame(ppu.framebuffer)
    renderer.root.after(16, run_frame)  # ~60 FPS

run_frame()
renderer.mainloop()
```

**VideCoding 检查点**：
- 游戏画面正常显示
- 按键盘有响应
- 无崩溃

---

## M4 完成标准

- [ ] 能正确渲染精灵
- [ ] 能处理精灵优先级
- [ ] 能检测精灵 0 碰撞
- [ ] 能正确处理滚动
- [ ] 键盘输入正常工作
- [ ] VBlank 和 NMI 正确触发
- [ ] 游戏画面完整，可响应输入
