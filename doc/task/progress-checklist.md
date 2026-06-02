# FC 模拟器开发进度清单

> 最后更新：2026-06-02
> 总体进度：M1 完成，M2-M5 待开发

---

## M1: ROM 加载 + CPU 骨架 [已完成]

### 1.1 项目基础结构搭建
- [x] 创建 src/ 目录
- [x] 创建 __init__.py
- [x] 创建 pyproject.toml
- [x] 创建 README.md
- [x] 创建 tests/ 目录

### 1.2 ROM 加载模块 (cartridge.py)
- [x] 定义 Cartridge 类
- [x] 实现 iNES 头部解析
- [x] 验证魔数 "NES\x1A"
- [x] 读取 PRG-ROM/CHR-ROM 银行数
- [x] 解析 Mapper 编号和镜像方式
- [x] 跳过 Trainer
- [x] 读取 PRG-ROM 数据
- [x] 读取 CHR-ROM 数据
- [x] 实现 cpu_read/cpu_write
- [x] 实现 ppu_read/ppu_write

### 1.3 CPU 模块骨架 (cpu.py)
- [x] 定义 CPU6502 类
- [x] 定义寄存器属性
- [x] 定义标志位常量
- [x] 实现 reset() 方法
- [x] 实现 _read/_write 方法
- [x] 实现 _get_flag/_set_flag 方法
- [x] 实现 step() 骨架
- [x] 实现 nmi/irq 骨架

### 1.4 总线模块 (bus.py)
- [x] 定义 Bus 类
- [x] 初始化 2KB RAM
- [x] 实现地址解码逻辑
- [x] 实现 read/write 方法
- [x] 连接组件引用

### 1.5 基础指令实现
- [x] 实现 NOP (0xEA)
- [x] 实现 LDA 立即寻址 (0xA9)
- [x] 实现 LDX 立即寻址 (0xA2)
- [x] 实现 LDY 立即寻址 (0xA0)
- [x] 实现 STA 绝对寻址 (0x8D)
- [x] 实现 STX 绝对寻址 (0x8E)
- [x] 实现 STY 绝对寻址 (0x8C)
- [x] 实现 JMP 绝对寻址 (0x4C)

---

## M2: 完整 CPU 指令集 [待开发]

### 2.1 所有寻址模式
- [ ] 立即寻址 (Immediate)
- [ ] 零页寻址 (Zero Page)
- [ ] 零页X寻址 (Zero Page,X)
- [ ] 零页Y寻址 (Zero Page,Y)
- [ ] 绝对寻址 (Absolute)
- [ ] 绝对X寻址 (Absolute,X)
- [ ] 绝对Y寻址 (Absolute,Y)
- [ ] X间接寻址 (Indirect,X)
- [ ] Y间接寻址 (Indirect,Y)
- [ ] 相对寻址 (Relative)
- [ ] 隐含寻址 (Implicit)
- [ ] 累加器寻址 (Accumulator)
- [ ] 间接寻址 (Indirect)

### 2.2 算术/逻辑指令
- [ ] ADC (加法)
- [ ] SBC (减法)
- [ ] INC/INX/INY (递增)
- [ ] DEC/DEX/DEY (递减)
- [ ] AND (逻辑与)
- [ ] ORA (逻辑或)
- [ ] EOR (逻辑异或)
- [ ] BIT (位测试)
- [ ] ASL (算术左移)
- [ ] LSR (逻辑右移)
- [ ] ROL (循环左移)
- [ ] ROR (循环右移)

### 2.3 比较/分支指令
- [ ] CMP (比较累加器)
- [ ] CPX (比较X)
- [ ] CPY (比较Y)
- [ ] BCC (进位清除分支)
- [ ] BCS (进位设置分支)
- [ ] BEQ (零标志分支)
- [ ] BNE (零标志清除分支)
- [ ] BMI (负数分支)
- [ ] BPL (正数分支)
- [ ] BVC (溢出清除分支)
- [ ] BVS (溢出设置分支)

### 2.4 栈操作指令
- [ ] PHA (压入累加器)
- [ ] PLA (弹出到累加器)
- [ ] PHP (压入状态寄存器)
- [ ] PLP (弹出到状态寄存器)
- [ ] TXS (X传到栈指针)
- [ ] TSX (栈指针传到X)

### 2.5 跳转/子程序指令
- [ ] JMP 绝对
- [ ] JMP 间接
- [ ] JSR (跳转到子程序)
- [ ] RTS (从子程序返回)
- [ ] RTI (从中断返回)
- [ ] BRK (中断指令)

### 2.6 中断处理
- [ ] NMI (不可屏蔽中断)
- [ ] IRQ (中断请求)
- [ ] Reset 中断
- [ ] 中断向量读取

### 2.7 测试验证
- [ ] 下载 nestest.nes
- [ ] 实现测试模式
- [ ] 解析测试输出
- [ ] 修复失败测试
- [ ] 通过所有测试

---

## M3: PPU 基础渲染 [待开发]

### 3.1 PPU 模块骨架 (ppu.py)
- [ ] 定义 PPU 类
- [ ] 定义寄存器属性
- [ ] 定义内部状态
- [ ] 定义帧缓冲区
- [ ] 实现 reset() 方法
- [ ] 实现 tick() 骨架

### 3.2 PPU 总线模块 (ppu_bus.py)
- [ ] 定义 PPUBus 类
- [ ] 初始化 Nametable RAM
- [ ] 实现地址解码
- [ ] 实现 read/write 方法
- [ ] 实现 Nametable 镜像

### 3.3 PPU 寄存器实现
- [ ] $2000 PPUCTRL 写入
- [ ] $2001 PPUMASK 写入
- [ ] $2002 PPUSTATUS 读取
- [ ] $2003 OAMADDR 写入
- [ ] $2004 OAMDATA 读写
- [ ] $2005 PPUSCROLL 写入
- [ ] $2006 PPUADDR 写入
- [ ] $2007 PPUDATA 读写

### 3.4 调色板数据 (palette.py)
- [ ] 定义 64 色 RGB 映射表
- [ ] 实现 get_color() 函数

### 3.5 背景渲染
- [ ] Tile 数据读取
- [ ] Nametable 读取
- [ ] Attribute Table 读取
- [ ] 背景像素颜色计算
- [ ] _render_scanline() 方法
- [ ] _get_background_pixel() 方法

### 3.6 基础渲染器 (renderer.py)
- [ ] 定义 Renderer 类
- [ ] 创建 Tkinter 窗口
- [ ] 创建 Canvas 组件
- [ ] 实现 render_frame() 方法
- [ ] 帧缓冲区到 PhotoImage 转换
- [ ] 实现 mainloop() 方法

### 3.7 整合测试
- [ ] 连接所有模块
- [ ] 实现基本帧循环
- [ ] 加载超级玛丽 ROM
- [ ] 渲染第一帧背景
- [ ] 验证画面正确性

---

## M4: 完整 PPU + 输入 [待开发]

### 4.1 精灵渲染
- [ ] OAM 数据结构
- [ ] 精灵属性解析
- [ ] 精灵优先级处理
- [ ] 精灵调色板
- [ ] 水平/垂直翻转
- [ ] 8x8 和 8x16 模式
- [ ] _get_sprite_pixel() 方法
- [ ] _evaluate_sprites() 方法

### 4.2 滚动实现
- [ ] 水平滚动
- [ ] 垂直滚动
- [ ] 滚动寄存器
- [ ] 精细滚动
- [ ] Nametable 切换

### 4.3 输入模块 (input.py)
- [ ] 定义 Controller 类
- [ ] 定义按钮常量
- [ ] 定义键位映射表
- [ ] 实现 write() 方法
- [ ] 实现 read() 方法
- [ ] 实现 key_press() 方法
- [ ] 实现 key_release() 方法

### 4.4 键盘事件处理
- [ ] 绑定键盘事件
- [ ] KeyPress 事件处理
- [ ] KeyRelease 事件处理
- [ ] 连接到 Controller

### 4.5 精灵 0 碰撞检测
- [ ] 碰撞检测逻辑
- [ ] 设置 PPUSTATUS 标志

### 4.6 VBlank 与 NMI 触发
- [ ] 扫描线 241 设置 VBlank
- [ ] 触发 CPU NMI
- [ ] 扫描线 261 重置 VBlank
- [ ] 帧完成标志

### 4.7 整合测试
- [ ] 连接所有模块
- [ ] 完整帧循环
- [ ] 渲染背景和精灵
- [ ] 响应键盘输入
- [ ] 验证游戏可玩性

---

## M5: 超级玛丽可玩 [待开发]

### 5.1 完善 CPU-PPU 同步
- [ ] 1:3 时钟比
- [ ] 周期精确 CPU 执行
- [ ] PPU 同步推进
- [ ] 跨扫描线指令处理
- [ ] 精确帧时序

### 5.2 帧率控制
- [ ] 帧时间测量
- [ ] 帧率限制
- [ ] Tkinter after() 定时器
- [ ] 避免阻塞 UI
- [ ] 帧率统计显示

### 5.3 完整主循环 (emulator.py)
- [ ] 定义 Emulator 类
- [ ] 初始化所有组件
- [ ] 连接组件引用
- [ ] 实现 run() 方法
- [ ] 实现 _run_frame() 方法
- [ ] 实现 _tick() 同步方法
- [ ] 异常和错误处理

### 5.4 调试与问题修复
- [ ] 调试日志输出
- [ ] 寄存器状态显示
- [ ] 内存查看功能
- [ ] 修复渲染问题
- [ ] 修复时序问题
- [ ] 性能优化

### 5.5 完整游戏测试
- [ ] 加载超级玛丽 ROM
- [ ] 显示标题画面
- [ ] 响应 Start 键
- [ ] 显示第一关画面
- [ ] 控制玛丽移动
- [ ] 跳跃功能
- [ ] 碰撞检测
- [ ] 通过第一关
- [ ] 无崩溃或卡死

---

## 扩展功能 [待开发]

### FR-07: APU 声音模拟
- [ ] APU 模块骨架
- [ ] 脉冲波声道
- [ ] 三角波声道
- [ ] 噪声声道
- [ ] 音频输出

### FR-08: 即时存档
- [ ] 状态序列化
- [ ] 状态反序列化
- [ ] 存档槽位管理

### FR-09: 更多 Mapper
- [ ] Mapper 1 (MMC1)
- [ ] Mapper 2 (UxROM)
- [ ] Mapper 4 (MMC3)

---

## 进度统计

| 里程碑 | 总任务数 | 已完成 | 进度 |
|--------|----------|--------|------|
| M1 | 35 | 35 | 100% |
| M2 | 65 | 0 | 0% |
| M3 | 40 | 0 | 0% |
| M4 | 45 | 0 | 0% |
| M5 | 35 | 0 | 0% |
| **总计** | **220** | **35** | **16%** |
