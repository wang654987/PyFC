# FC 模拟器开发任务总览

> 项目：PyFC（Python FC Emulator）
> 目标：实现能运行《超级玛丽》的 FC/NES 模拟器
> 最后更新：2026-06-02

---

## 任务分解原则

1. **小任务粒度**：每个小任务可在 1-2 小时内完成
2. **适合 VideCoding**：任务明确、可独立编码、可测试验证
3. **渐进式开发**：按里程碑顺序推进，每个阶段可独立运行验证

---

## 里程碑与任务清单

### M1: ROM 加载 + CPU 骨架
- [x] 1.1 项目基础结构搭建
- [x] 1.2 ROM 加载模块（cartridge.py）
- [x] 1.3 CPU 模块骨架（cpu.py）
- [x] 1.4 总线模块（bus.py）
- [x] 1.5 基础指令实现（NOP, LDA, STA 等）

**详细任务**：[m1-rom-cpu.md](m1-rom-cpu.md)

---

### M2: 完整 CPU 指令集
- [ ] 2.1 所有寻址模式实现
- [ ] 2.2 算术/逻辑指令（ADC, SBC, AND, ORA, EOR）
- [ ] 2.3 比较/分支指令（CMP, CPX, CPY, BEQ, BNE 等）
- [ ] 2.4 栈操作指令（PHA, PLA, PHP, PLP）
- [ ] 2.5 跳转/子程序指令（JMP, JSR, RTS, RTI）
- [ ] 2.6 中断处理（NMI, IRQ, Reset）
- [ ] 2.7 通过 nestest.nes 测试验证

**详细任务**：[m2-cpu-instructions.md](m2-cpu-instructions.md)

---

### M3: PPU 基础渲染
- [ ] 3.1 PPU 模块骨架（ppu.py）
- [ ] 3.2 PPU 总线模块（ppu_bus.py）
- [ ] 3.3 PPU 寄存器实现（$2000-$2007）
- [ ] 3.4 调色板数据（palette.py）
- [ ] 3.5 背景渲染（Nametable + Attribute Table）
- [ ] 3.6 基础渲染器（renderer.py）
- [ ] 3.7 能显示超级玛丽背景画面

**详细任务**：[m3-ppu-basic.md](m3-ppu-basic.md)

---

### M4: 完整 PPU + 输入
- [ ] 4.1 精灵渲染（OAM + Sprites）
- [ ] 4.2 滚动（Scroll）实现
- [ ] 4.3 输入模块（input.py）
- [ ] 4.4 键盘事件处理
- [ ] 4.5 精灵 0 碰撞检测
- [ ] 4.6 VBlank 与 NMI 触发
- [ ] 4.7 画面能正确显示并响应键盘

**详细任务**：[m4-ppu-input.md](m4-ppu-input.md)

---

### M5: 超级玛丽可玩
- [ ] 5.1 完善 CPU-PPU 同步
- [ ] 5.2 帧率控制（60 FPS）
- [ ] 5.3 完整主循环（emulator.py）
- [ ] 5.4 调试与问题修复
- [ ] 5.5 能正常运行超级玛丽第一关

**详细任务**：[m5-mario-playable.md](m5-mario-playable.md)

---

## 扩展功能（后续版本）

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
- [ ] Mapper 1（MMC1）
- [ ] Mapper 2（UxROM）
- [ ] Mapper 4（MMC3）

---

## 进度统计

| 里程碑 | 总任务数 | 已完成 | 进度 |
|--------|----------|--------|------|
| M1 | 5 | 5 | 100% |
| M2 | 7 | 0 | 0% |
| M3 | 7 | 0 | 0% |
| M4 | 7 | 0 | 0% |
| M5 | 5 | 0 | 0% |
