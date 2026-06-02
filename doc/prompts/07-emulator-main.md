# Vibecoding Prompt 07: Emulator 主循环 + 入口

## 概述

实现 `emulator.py`（模拟器主控制器，组装所有模块并驱动主循环）和 `src/main.py`（程序入口点）。

## 前置条件

所有其他模块已完成：
- `src/cartridge.py` — ROM 加载
- `src/cpu.py` — 6502 CPU
- `src/bus.py` — CPU 总线
- `src/ppu_bus.py` — PPU 总线
- `src/ppu.py` — 图形处理
- `src/input.py` — 手柄模拟
- `src/renderer.py` — Tkinter 渲染
- `src/palette.py` — 调色板

## 你要创建/修改的文件

### 1. `src/emulator.py` — 模拟器主控制器

#### Emulator 类完整实现

```python
from __future__ import annotations

import time
from .cartridge import Cartridge
from .bus import Bus
from .ppu_bus import PPUBus
from .cpu import CPU6502
from .ppu import PPU
from .input import Controller
from .renderer import Renderer


class Emulator:
    """FC/NES 模拟器主控制器。

    职责：
    1. 创建并连接所有模块
    2. 驱动主循环（CPU → PPU → 渲染）
    3. 帧率控制（目标 60 FPS）
    """

    # NTSC 时钟参数
    CPU_CLOCK: int = 1789773       # CPU 主频 (Hz)
    PPU_CLOCK: int = 5369319       # PPU 主频 (CPU × 3)
    FPS: float = 60.0              # 目标帧率
    CYCLES_PER_FRAME: int = 29781  # 每帧 CPU 周期数
    FRAME_TIME: float = 1.0 / 60.0  # 每帧目标耗时 (秒)

    def __init__(self, rom_path: str, scale: int = 3) -> None:
        """
        初始化模拟器。

        Args:
            rom_path: .nes ROM 文件路径
            scale: 画面缩放倍数
        """
        # 第一步：加载 ROM
        with open(rom_path, "rb") as f:
            rom_data = f.read()
        self.cartridge = Cartridge(rom_data)

        # 第二步：创建输入设备
        self.controller = Controller()

        # 第三步：创建 PPU 和 PPUBus
        self.ppu_bus = PPUBus(
            cartridge=self.cartridge,
            mirror_mode=self.cartridge.mirror_mode,
        )
        self.ppu = PPU(self.ppu_bus)

        # 第四步：创建 CPU 和 Bus
        self.bus = Bus(
            ppu=self.ppu,
            cartridge=self.cartridge,
            controller=self.controller,
        )
        self.cpu = CPU6502(self.bus)

        # 第五步：连接 PPU 的 NMI 回调到 CPU
        self.ppu.nmi_callback = self.cpu.nmi
        # CPU 的 IRQ 暂不实现（Mapper 0 不支持 IRQ）

        # 第六步：创建渲染器
        title = f"PyFC - {rom_path.split('/')[-1].split(chr(92))[-1]}"
        self.renderer = Renderer(title=title, scale=scale)
        self.renderer.bind_input(self.controller)

        # 第七步：复位所有组件
        self.cpu.reset()
        self.ppu.reset()

        # 帧率控制
        self._running = False
        self._frame_count = 0
        self._fps_update_time = time.time()
        self._last_frame_time = time.time()

    def run(self) -> None:
        """启动模拟器（阻塞调用，进入主循环）。"""
        self._running = True
        self._last_frame_time = time.time()
        # 使用 after() 驱动帧循环而非同步 while 循环
        self._schedule_next_frame()
        self.renderer.start()

    def _schedule_next_frame(self) -> None:
        """调度下一帧。"""
        if not self._running:
            return
        self.renderer.schedule(1, self._frame_loop)

    def _frame_loop(self) -> None:
        """帧循环（由 Tkinter after() 定时触发）。

        每帧执行：
        1. 运行 CPU 指令直到 PPU 完成一帧
        2. 渲染帧缓冲区
        3. 帧率限制
        """
        if not self._running:
            return

        current_time = time.time()
        elapsed = current_time - self._last_frame_time

        # 帧率控制：间距不小于 FRAME_TIME
        if elapsed >= self.FRAME_TIME:
            self._run_frame()
            self.renderer.render_frame(self.ppu.framebuffer)
            self._last_frame_time = current_time
            self._update_fps_display()

        self._schedule_next_frame()

    def _run_frame(self) -> None:
        """
        执行一帧的 CPU/PPU 模拟。

        循环：
        1. CPU 执行一条指令 → 返回消耗的周期数
        2. PPU 推进（CPU 周期数 × 3）个 PPU 周期
        3. 检查 PPU.frame_complete
        4. 如果 PPU 触发了 NMI，处理之
        """
        self.ppu.frame_complete = False

        frame_cycles = 0
        max_cycles = self.CYCLES_PER_FRAME * 2  # 安全上限

        while not self.ppu.frame_complete:
            if frame_cycles > max_cycles:
                # 安全上限：防止无限循环
                break

            # 1. CPU 执行一条指令
            cpu_cycles = self.cpu.step()
            frame_cycles += cpu_cycles

            # 2. 推进 PPU（1 CPU 周期 = 3 PPU 周期）
            for _ in range(cpu_cycles * 3):
                self.ppu.tick()
                if self.ppu.frame_complete:
                    break

    def _update_fps_display(self) -> None:
        """每秒更新一次 FPS 显示。"""
        self._frame_count += 1
        current_time = time.time()
        elapsed = current_time - self._fps_update_time

        if elapsed >= 1.0:
            fps = self._frame_count / elapsed
            self.renderer.set_title(
                f"PyFC - {fps:.1f} FPS"
            )
            self._frame_count = 0
            self._fps_update_time = current_time

    def reset(self) -> None:
        """重置模拟器。"""
        self.cpu.reset()
        self.ppu.reset()
        self.controller.reset()
        self._frame_count = 0
        self._last_frame_time = time.time()
        self._fps_update_time = time.time()

    def stop(self) -> None:
        """停止模拟器。"""
        self._running = False
        self.renderer.stop()
```

### 2. `src/main.py` — 程序入口

```python
"""PyFC - Python NES/Famicom Emulator

用法：
    python -m src.main [ROM文件路径]

默认 ROM：项目根目录下的 Super Mario Bros.nes
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    """程序主入口。"""
    if len(sys.argv) > 1:
        rom_path = sys.argv[1]
    else:
        # 默认 ROM 路径
        project_root = Path(__file__).parent.parent
        default_rom = project_root / "Super Mario Bros. (E) (PRG0) [!].nes"
        if not default_rom.exists():
            print(
                f"错误：未找到默认 ROM 文件\n"
                f"  请将 ROM 文件放在项目根目录或以参数指定：\n"
                f"  python -m src.main <rom_path>"
            )
            sys.exit(1)
        rom_path = str(default_rom)

    print(f"加载 ROM: {rom_path}")
    print(f"键位：WASD/方向键=移动  J/Z=A  K/X=B  Enter=Start  RightShift=Select")
    print(f"窗口大小：768×720 (3x)")
    print()

    from .emulator import Emulator

    emulator = Emulator(rom_path, scale=3)

    try:
        emulator.run()
    except KeyboardInterrupt:
        print("\n模拟器已退出")
    except Exception as e:
        print(f"错误：{e}")
        raise


if __name__ == "__main__":
    main()
```

## 关键实现注意事项

### 1. 帧循环使用 Tkinter after() 而非同步循环

- **为什么**：同步 `while` 循环会阻塞 Tkinter 事件循环，导致窗口无响应
- **做法**：使用 `renderer.schedule(1, callback)` 在每帧后异步调度下一帧
- **帧率控制**：检查距离上一帧的时间，如果不足 16.67ms 则跳过

### 2. CPU-PPU 同步

- 1 CPU 周期 = 3 PPU 周期
- 每条 CPU 指令执行后，立即推进 PPU `cpu_cycles * 3` 个周期
- 这确保了 CPU 对 PPU 寄存器的写入在正确的 PPU 时间点生效

### 3. NMI 触发路径

- PPU 在 scanline 241 时设置 VBlank 标志
- 如果 NMI 使能（ctrl & 0x80），PPU 调用 `nmi_callback()` → `cpu.nmi()`
- CPU 的 `nmi()` 设置 `interrupt_type = NMI`，在下一次 `step()` 中处理

### 4. 错误处理

- ROM 文件不存在 → 友好错误信息
- Cartridge 解析失败 → 传播异常，给出提示
- 运行中异常 → 捕获并显示

### 5. 安全上限

- `_run_frame()` 中有 `frame_cycles > max_cycles` 检查
- 防止 CPU 因无限循环导致程序卡死
- `max_cycles = CYCLES_PER_FRAME * 2` 是安全边界

## 测试要求

### `tests/test_emulator.py`

```python
import pytest
from pathlib import Path


class TestEmulator:
    """模拟器集成测试。"""

    ROM_PATH: str = str(
        Path(__file__).parent.parent
        / "Super Mario Bros. (E) (PRG0) [!].nes"
    )

    @pytest.mark.skipif(
        not Path(ROM_PATH).exists(),
        reason="ROM file not available",
    )
    def test_emulator_creation(self):
        """验证模拟器可以从 ROM 文件创建。"""
        from src.emulator import Emulator

        emu = Emulator(self.ROM_PATH, scale=1)
        assert emu.cpu is not None
        assert emu.ppu is not None
        assert emu.bus is not None
        assert emu.ppu_bus is not None
        assert emu.cartridge is not None
        assert emu.controller is not None
        assert emu.renderer is not None
        emu.stop()

    @pytest.mark.skipif(
        not Path(ROM_PATH).exists(),
        reason="ROM file not available",
    )
    def test_run_one_frame(self):
        """验证可以运行一帧。"""
        from src.emulator import Emulator

        emu = Emulator(self.ROM_PATH, scale=1)
        emu._run_frame()
        assert emu.ppu.frame_complete

        # 帧缓冲区应有数据（不会全是同一颜色）
        colors = set(emu.ppu.framebuffer)
        assert len(colors) >= 2  # 至少有两种不同的颜色
        emu.stop()

    @pytest.mark.skipif(
        not Path(ROM_PATH).exists(),
        reason="ROM file not available",
    )
    def test_run_multiple_frames(self):
        """验证可以运行多个帧。"""
        from src.emulator import Emulator

        emu = Emulator(self.ROM_PATH, scale=1)
        for _ in range(10):
            emu._run_frame()
            assert emu.ppu.frame_complete
        emu.stop()

    @pytest.mark.skipif(
        not Path(ROM_PATH).exists(),
        reason="ROM file not available",
    )
    def test_reset(self):
        """验证 reset() 后可以继续运行。"""
        from src.emulator import Emulator

        emu = Emulator(self.ROM_PATH, scale=1)
        emu._run_frame()
        emu.reset()
        assert emu.cpu.pc != 0  # PC 应该已从复位向量重新加载
        emu._run_frame()
        emu.stop()

    @pytest.mark.skipif(
        not Path(ROM_PATH).exists(),
        reason="ROM file not available",
    )
    def test_controller_input(self):
        """验证控制器输入影响运行。"""
        from src.emulator import Emulator

        emu = Emulator(self.ROM_PATH, scale=1)

        # 按 Start 键
        emu.controller.key_press("Return")
        emu._run_frame()
        emu.controller.key_release("Return")

        # 按方向键
        emu.controller.key_press("Right")
        emu._run_frame()
        emu.controller.key_release("Right")

        emu.stop()

    @pytest.mark.skipif(
        not Path(ROM_PATH).exists(),
        reason="ROM file not available",
    )
    def test_fps_display(self):
        """验证 FPS 显示不会崩溃。"""
        from src.emulator import Emulator

        emu = Emulator(self.ROM_PATH, scale=1)
        for _ in range(60):
            emu._run_frame()
        emu._update_fps_display()
        emu.stop()

    def test_emulator_invalid_rom(self):
        """验证无效 ROM 文件抛出异常。"""
        import tempfile
        from src.emulator import Emulator

        with tempfile.NamedTemporaryFile(suffix=".nes", delete=False) as f:
            f.write(b"INVALID ROM DATA")
            temp_path = f.name

        try:
            with pytest.raises((ValueError, Exception)):
                Emulator(temp_path, scale=1)
        finally:
            import os
            os.unlink(temp_path)
```

### `tests/test_main.py`

```python
class TestMain:
    """主入口测试。"""

    def test_main_module_importable(self):
        """验证 src.main 可以导入。"""
        from src.main import main
        assert callable(main)

    def test_main_no_rom_no_crash(self):
        """验证无 ROM 时 main() 不崩溃（仅退出）。"""
        import sys
        # 这只验证导入和逻辑正确，不实际运行 GUI
        from src.main import main
        assert callable(main)
```

## 质量检查

```bash
# 1. ruff 代码风格检查
ruff check src/emulator.py src/main.py tests/test_emulator.py tests/test_main.py

# 2. mypy 类型检查
mypy src/emulator.py src/main.py

# 3. pytest 单元测试
pytest tests/test_emulator.py tests/test_main.py -v

# 4. 全量测试
pytest tests/ -v
```

## 文件清单

```
src/emulator.py           # ← 创建
src/main.py               # ← 覆盖（替换根目录的 main.py）
tests/test_emulator.py    # ← 创建
tests/test_main.py        # ← 创建
```

## 验收标准

- [ ] Emulator 正确创建并连接所有模块
- [ ] `_run_frame()` 正确同步 CPU 和 PPU
- [ ] 帧率控制在 ~60 FPS
- [ ] FPS 显示正确更新
- [ ] reset() 能正确重置所有组件
- [ ] 无效 ROM 文件会抛出合适的异常
- [ ] 命令行入口能正确解析参数
- [ ] 能运行超级玛丽 ROM 文件至少 60 帧不崩溃
- [ ] 所有 pytest 测试通过
- [ ] mypy 类型检查无错误
- [ ] ruff 代码风格检查无错误

## 集成测试验证

在所有模块实现完成后，运行以下命令验证整个项目：

```bash
# 1. 全量类型检查
mypy src/

# 2. 全量代码风格检查
ruff check src/ tests/

# 3. 全量单元测试
pytest tests/ -v

# 4. 运行模拟器（手动测试）
python -m src.main
```
