# M5: 超级玛丽可玩

> 目标：能正常运行超级玛丽第一关
> 验收标准：游戏流畅运行，可完整通关第一关

---

## 任务清单

### 5.1 完善 CPU-PPU 同步

**目标**：实现精确的 CPU-PPU 时钟同步

- [ ] 实现 1:3 时钟比（CPU:PPU）
- [ ] 实现周期精确的 CPU 执行
- [ ] 实现 PPU 随 CPU 同步推进
- [ ] 处理跨扫描线的指令执行
- [ ] 实现精确的帧时序

**同步实现**：
```python
def _run_frame(self):
    """执行一帧"""
    self.ppu.frame_complete = False
    
    while not self.ppu.frame_complete:
        # 执行一条 CPU 指令
        cpu_cycles = self.cpu.step()
        
        # 同步推进 PPU（1 CPU = 3 PPU）
        for _ in range(cpu_cycles * 3):
            self.ppu.tick()
            
            # 检查 NMI
            if self.ppu.nmi_pending:
                self.cpu.nmi()
                self.ppu.nmi_pending = False
            
            # 检查 IRQ
            if self.ppu.irq_pending:
                self.cpu.irq()
                self.ppu.irq_pending = False
```

**VideCoding 检查点**：
```python
# 运行一帧检查同步
emulator._run_frame()
assert ppu.scanline == 0  # 帧结束后回到起始
assert ppu.cycle == 0
```

---

### 5.2 帧率控制（60 FPS）

**目标**：维持稳定的 60 FPS 帧率

- [ ] 实现帧时间测量
- [ ] 实现帧率限制
- [ ] 使用 Tkinter after() 定时器
- [ ] 避免阻塞 UI 线程
- [ ] 实现帧率统计显示（可选）

**帧率控制实现**：
```python
import time

class Emulator:
    FPS = 60
    FRAME_TIME = 1.0 / FPS
    
    def __init__(self):
        self.last_frame_time = time.time()
        self.frame_count = 0
        self.fps_timer = time.time()
    
    def run(self):
        """启动模拟器"""
        self._run_frame()
        self.renderer.root.after(1, self._frame_loop)
        self.renderer.mainloop()
    
    def _frame_loop(self):
        """帧循环"""
        current_time = time.time()
        elapsed = current_time - self.last_frame_time
        
        if elapsed >= self.FRAME_TIME:
            self._run_frame()
            self.renderer.render_frame(self.ppu.framebuffer)
            self.last_frame_time = current_time
            self.frame_count += 1
            
            # FPS 统计
            if current_time - self.fps_timer >= 1.0:
                fps = self.frame_count / (current_time - self.fps_timer)
                self.renderer.set_title(f"PyFC - {fps:.1f} FPS")
                self.frame_count = 0
                self.fps_timer = current_time
        
        self.renderer.root.after(1, self._frame_loop)
```

**VideCoding 检查点**：
```python
# 检查帧率
start = time.time()
for _ in range(60):
    emulator._run_frame()
elapsed = time.time() - start
assert 0.9 < elapsed < 1.1  # 约 1 秒
```

---

### 5.3 完整主循环（emulator.py）

**目标**：实现完整的模拟器主控制器

- [ ] 定义 Emulator 类
- [ ] 初始化所有组件
- [ ] 连接组件引用
- [ ] 实现 run() 方法
- [ ] 实现 _run_frame() 方法
- [ ] 实现 _tick() 同步方法
- [ ] 处理异常和错误

**Emulator 完整实现**：
```python
class Emulator:
    def __init__(self, rom_path: str, scale: int = 3):
        # 加载 ROM
        self.cartridge = Cartridge(rom_path)
        
        # 创建总线
        self.bus = Bus()
        self.ppu_bus = PPUBus(self.cartridge)
        
        # 创建组件
        self.cpu = CPU6502(self.bus)
        self.ppu = PPU(self.ppu_bus)
        self.controller = Controller()
        self.renderer = Renderer(self, scale)
        
        # 连接组件
        self.bus.cpu = self.cpu
        self.bus.ppu = self.ppu
        self.bus.cartridge = self.cartridge
        self.bus.controller = self.controller
        self.ppu.ppu_bus = self.ppu_bus
        self.ppu.nmi_callback = self.cpu.nmi
        
        # 初始化
        self.cpu.reset()
        self.ppu.reset()
        
        # 帧率控制
        self.last_frame_time = time.time()
        self.frame_count = 0
        self.fps_timer = time.time()
        self.running = True
    
    def run(self):
        """启动模拟器"""
        self.renderer.bind_input(self.controller)
        self._frame_loop()
        self.renderer.mainloop()
    
    def _frame_loop(self):
        """帧循环"""
        if not self.running:
            return
        
        current_time = time.time()
        elapsed = current_time - self.last_frame_time
        
        if elapsed >= self.FRAME_TIME:
            self._run_frame()
            self.renderer.render_frame(self.ppu.framebuffer)
            self.last_frame_time = current_time
            self._update_fps()
        
        self.renderer.root.after(1, self._frame_loop)
    
    def _run_frame(self):
        """执行一帧"""
        self.ppu.frame_complete = False
        
        while not self.ppu.frame_complete:
            cpu_cycles = self.cpu.step()
            self._tick(cpu_cycles)
    
    def _tick(self, cpu_cycles: int):
        """同步 CPU 和 PPU"""
        for _ in range(cpu_cycles * 3):
            self.ppu.tick()
            
            if self.ppu.nmi_pending:
                self.cpu.nmi()
                self.ppu.nmi_pending = False
    
    def _update_fps(self):
        """更新 FPS 显示"""
        self.frame_count += 1
        current_time = time.time()
        
        if current_time - self.fps_timer >= 1.0:
            fps = self.frame_count / (current_time - self.fps_timer)
            self.renderer.root.title(f"PyFC - {fps:.1f} FPS")
            self.frame_count = 0
            self.fps_timer = current_time
```

**VideCoding 检查点**：
```python
# 初始化模拟器
emu = Emulator("Super Mario Bros. (E) (PRG0) [!].nes", scale=2)
assert emu.cpu is not None
assert emu.ppu is not None
assert emu.renderer is not None
```

---

### 5.4 调试与问题修复

**目标**：解决运行时问题

- [ ] 实现调试日志输出
- [ ] 实现寄存器状态显示
- [ ] 实现内存查看功能
- [ ] 修复常见的渲染问题
- [ ] 修复时序问题
- [ ] 优化性能

**调试工具**：
```python
class Debugger:
    def __init__(self, emulator):
        self.emu = emulator
        self.breakpoints = set()
        self.log_enabled = False
    
    def log_state(self):
        """输出 CPU 状态"""
        cpu = self.emu.cpu
        print(f"PC: ${cpu.pc:04X}  "
              f"A: ${cpu.a:02X}  "
              f"X: ${cpu.x:02X}  "
              f"Y: ${cpu.y:02X}  "
              f"SP: ${cpu.sp:02X}  "
              f"Status: ${cpu.status:02X}")
    
    def dump_memory(self, start: int, length: int):
        """输出内存内容"""
        for i in range(0, length, 16):
            addr = start + i
            hex_str = ' '.join(
                f"${self.emu.bus.read(addr + j):02X}"
                for j in range(min(16, length - i))
            )
            print(f"${addr:04X}: {hex_str}")
    
    def check_instruction(self, opcode: int):
        """检查指令是否实现"""
        if opcode not in INSTRUCTION_TABLE:
            print(f"Warning: Unimplemented opcode ${opcode:02X}")
```

**VideCoding 检查点**：
```python
# 运行时无警告
debugger = Debugger(emulator)
debugger.log_enabled = True
# 运行几帧检查输出
```

---

### 5.5 完整游戏测试

**目标**：验证超级玛丽可玩性

- [ ] 加载超级玛丽 ROM
- [ ] 显示标题画面
- [ ] 响应 Start 键开始游戏
- [ ] 显示第一关画面
- [ ] 控制玛丽移动
- [ ] 跳跃功能正常
- [ ] 碰撞检测正常
- [ ] 能通过第一关
- [ ] 无崩溃或卡死

**测试流程**：
```python
# 完整游戏测试
def test_game():
    emu = Emulator("Super Mario Bros. (E) (PRG0) [!].nes")
    
    # 运行到标题画面
    for _ in range(180):  # 约 3 秒
        emu._run_frame()
    
    # 按 Start 键
    emu.controller.key_press('Return')
    for _ in range(10):
        emu._run_frame()
    emu.controller.key_release('Return')
    
    # 运行游戏
    for _ in range(300):  # 约 5 秒
        emu._run_frame()
        # 模拟输入
        emu.controller.key_press('Right')
        if random.random() < 0.1:
            emu.controller.key_press('z')  # 跳跃
    
    print("Game test completed successfully")
```

**VideCoding 检查点**：
- 标题画面正常显示
- 按 Start 能开始游戏
- 玛丽能移动和跳跃
- 无崩溃

---

## 优化建议

### 性能优化
- [ ] 使用 NumPy 加速像素处理（可选）
- [ ] 优化 PPU 渲染循环
- [ ] 减少函数调用开销
- [ ] 使用缓存减少重复计算

### 用户体验优化
- [ ] 添加暂停功能
- [ ] 添加重置功能
- [ ] 添加全屏切换
- [ ] 添加音量控制（如果实现 APU）
- [ ] 添加快捷键提示

### 代码质量优化
- [ ] 添加类型注解
- [ ] 添加文档字符串
- [ ] 添加单元测试
- [ ] 重构重复代码

---

## M5 完成标准

- [ ] CPU-PPU 同步正确
- [ ] 帧率稳定在 60 FPS 左右
- [ ] 主循环稳定运行
- [ ] 无明显 Bug
- [ ] 能正常运行超级玛丽
- [ ] 能通过第一关
- [ ] 用户体验流畅
