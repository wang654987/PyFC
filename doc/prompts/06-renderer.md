# Vibecoding Prompt 06: Tkinter 渲染器

## 概述

实现 `Renderer` 类，负责创建 Tkinter 窗口、将 PPU 帧缓冲区渲染到 Canvas、以及绑定键盘事件到控制器。

## 前置条件

- `src/input.py` 的 Controller 接口（`key_press` / `key_release`）
- Python 标准库 `tkinter` 可用
- 帧缓冲区格式：`list[int]`，长度 256×240，每个元素是 0xRRGGBB 格式的颜色值

## 你要创建/修改的文件

### `src/renderer.py` — Tkinter 渲染窗口

#### Renderer 类完整实现

```python
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .input import Controller

class Renderer:
    """Tkinter 渲染器 — 负责画面显示和键盘事件处理。

    设计要点：
    - 使用 Tkinter Canvas 显示画面
    - 支持整数倍缩放（默认 3x）
    - 使用 PhotoImage 的 put() 方法批量写入像素（性能优化）
    - 键盘事件转发给 Controller
    """

    WIDTH: int = 256   # NES 原始宽度
    HEIGHT: int = 240  # NES 原始高度

    def __init__(self, title: str = "PyFC - FC Emulator", scale: int = 3) -> None:
        """
        初始化渲染窗口。

        Args:
            title: 窗口标题
            scale: 画面缩放倍数（正整数，推荐 2 或 3）
        """
        self.scale = max(1, scale)
        self.root = tk.Tk()
        self.root.title(title)
        self.root.resizable(False, False)

        # 创建 Canvas
        canvas_width = self.WIDTH * self.scale
        canvas_height = self.HEIGHT * self.scale
        self.canvas = tk.Canvas(
            self.root,
            width=canvas_width,
            height=canvas_height,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack()

        # 创建 PhotoImage（用于帧缓冲渲染）
        self._photo: tk.PhotoImage | None = None
        self._create_photo()

        self._running = False

    def _create_photo(self) -> None:
        """创建/重新创建 PhotoImage 对象。"""
        self._photo = tk.PhotoImage(width=self.WIDTH, height=self.HEIGHT)
        self.canvas.create_image(
            0, 0,
            image=self._photo,
            anchor="nw",
            tags="frame",
        )

    def render_frame(self, framebuffer: list[int]) -> None:
        """
        将帧缓冲区渲染到 Canvas。

        Args:
            framebuffer: 长度为 256*240 的列表，每个元素是 0xRRGGBB 颜色值

        实现策略：
        - 使用 PhotoImage 的 put() 方法按行批量写入（比逐像素快很多）
        - 如果 scale > 1，先创建原始大小的 PhotoImage，再使用 zoom()
        - 每行像素构造一个颜色字符串块
        """
        if self._photo is None:
            self._create_photo()

        # 性能优化：按行批量写入
        for y in range(self.HEIGHT):
            row_start = y * self.WIDTH
            row_pixels: list[str] = []

            for x in range(self.WIDTH):
                rgb = framebuffer[row_start + x]
                r = (rgb >> 16) & 0xFF
                g = (rgb >> 8) & 0xFF
                b = rgb & 0xFF
                row_pixels.append(f"#{r:02x}{g:02x}{b:02x}")

            # 一次性写入整行
            row_str = "{" + " ".join(row_pixels) + "}" + ""
            self._photo.put(row_str, to=(0, y))

        # 缩放处理
        if self.scale > 1:
            # 删除旧缩放图像，创建新的
            self.canvas.delete("scaled")
            zoomed = self._photo.zoom(self.scale, self.scale)
            self.canvas.create_image(
                0, 0,
                image=zoomed,
                anchor="nw",
                tags="scaled",
            )
            # 保存引用防止被 GC
            self._zoomed_photo = zoomed

        self.canvas.update_idletasks()

    def bind_input(self, controller: Controller) -> None:
        """
        绑定键盘事件到控制器。

        绑定 <KeyPress> 和 <KeyRelease> 事件，
        转发给 controller.key_press() 和 controller.key_release()。

        Args:
            controller: Controller 实例
        """
        # 使用 lambda 捕获 controller 引用
        def on_key_press(event: tk.Event[tk.Tk]) -> None:
            controller.key_press(event.keysym)

        def on_key_release(event: tk.Event[tk.Tk]) -> None:
            controller.key_release(event.keysym)

        self.root.bind("<KeyPress>", on_key_press)
        self.root.bind("<KeyRelease>", on_key_release)
        self.root.focus_set()

    def set_title(self, title: str) -> None:
        """更新窗口标题。"""
        self.root.title(title)

    def schedule(self, delay_ms: int, callback) -> None:
        """
        使用 Tkinter after() 定时调用回调。

        Args:
            delay_ms: 延迟毫秒数
            callback: 回调函数（无参数）
        """
        self.root.after(delay_ms, callback)

    def start(self) -> None:
        """启动 Tkinter 主循环（阻塞调用）。"""
        self._running = True
        self.root.mainloop()

    def stop(self) -> None:
        """停止渲染器。"""
        self._running = False
        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError:
            pass

    def update(self) -> None:
        """更新 Tkinter 事件循环（非阻塞）。"""
        self.root.update()
```

## 测试要求

### `tests/test_renderer.py`

由于 Tkinter 渲染器涉及 GUI（难以完全自动化测试），测试策略如下：

1. **Renderer 不需要完整的 pytest 测试**（Tkinter 主循环会阻塞测试）
2. 但需要编写以下最小测试来验证基础功能：

```python
import tkinter as tk
import pytest


class TestRendererBasic:
    """Renderer 基础测试（不涉及主循环）。"""

    def test_renderer_creation(self):
        """验证 Renderer 可以创建（不要进入主循环）。"""
        from src.renderer import Renderer

        renderer = Renderer("Test", scale=2)
        assert renderer.WIDTH == 256
        assert renderer.HEIGHT == 240
        assert renderer.scale == 2
        renderer.root.destroy()

    def test_renderer_default_scale(self):
        """默认缩放应为 3。"""
        from src.renderer import Renderer

        renderer = Renderer()
        assert renderer.scale == 3
        renderer.root.destroy()

    def test_renderer_scale_minimum(self):
        """缩放倍数最小为 1。"""
        from src.renderer import Renderer

        renderer = Renderer(scale=0)
        assert renderer.scale == 1
        renderer.root.destroy()

    def test_render_frame_no_crash(self):
        """render_frame 应该不崩溃（使用全黑帧缓冲区）。"""
        from src.renderer import Renderer

        renderer = Renderer("Test", scale=1)
        black_frame = [0x000000] * (256 * 240)
        renderer.render_frame(black_frame)
        renderer.root.destroy()

    def test_render_frame_with_colors(self):
        """render_frame 应该正确处理有颜色的帧缓冲区。"""
        from src.renderer import Renderer

        renderer = Renderer("Test", scale=1)
        # 创建渐变帧缓冲区
        frame: list[int] = []
        for y in range(240):
            for x in range(256):
                r = (x * 255) // 255
                g = (y * 255) // 239
                b = 128
                frame.append((r << 16) | (g << 8) | b)
        renderer.render_frame(frame)
        renderer.root.destroy()

    def test_set_title(self):
        """set_title 应该更新窗口标题。"""
        from src.renderer import Renderer

        renderer = Renderer("PyFC", scale=1)
        renderer.set_title("New Title")
        # Tkinter 标题更新不抛异常即为通过
        renderer.root.destroy()

    def test_stop(self):
        """stop 应该正常关闭窗口。"""
        from src.renderer import Renderer

        renderer = Renderer("Test", scale=1)
        renderer.stop()
        # 不应抛出异常
```

测试注意事项：
- 每个测试必须调用 `renderer.root.destroy()` 清理资源
- 不要在测试中调用 `renderer.start()`（会阻塞）
- Tkinter 的 `bind_input` 需要 Controller 实例，可选测试

## 质量检查

```bash
# 1. ruff 代码风格检查
ruff check src/renderer.py tests/test_renderer.py

# 2. mypy 类型检查
mypy src/renderer.py

# 3. pytest 单元测试
pytest tests/test_renderer.py -v
```

## 重要实现注意事项

1. **PhotoImage.put() 性能**：
   - 使用 `put("{颜色字符串}", to=(x, y))` 格式
   - 颜色格式：`#rrggbb`（小写十六进制）
   - 按行批量写入比逐像素写入快 100 倍以上

2. **PhotoImage.zoom() 缩放**：
   - `zoom(x, y)` 返回新 PhotoImage，需要保存引用防止被 GC
   - scale=3 时 `zoom(3, 3)` 将 256×240 → 768×720

3. **键盘事件处理**：
   - Tkinter 的 `keysym` 对于字母键返回小写（如 "w", "a"）
   - 方向键返回 "Up", "Down", "Left", "Right"
   - Enter 键返回 "Return"
   - Right Shift 返回 "Shift_R"

4. **窗口焦点**：
   - `focus_set()` 确保键盘事件能被捕获
   - 建议在 `bind_input()` 中调用

## 与其他模块的接口

| 被依赖模块 | 使用方式 |
|-----------|---------|
| `emulator.py` | 创建 Renderer，调用 `render_frame()`、`bind_input()`、`schedule()`、`start()` |

## 文件清单

```
src/renderer.py           # ← 创建
tests/test_renderer.py    # ← 创建
```

## 验收标准

- [ ] Tkinter 窗口正确创建，Canvas 大小 = 256×scale × 240×scale
- [ ] render_frame() 正确将 RGB 缓冲区渲染为图像
- [ ] 缩放功能正确（zoom 倍数）
- [ ] bind_input() 正确绑定键盘事件并转发给 Controller
- [ ] schedule() 使用 after() 定时回调
- [ ] stop() 正常关闭窗口
- [ ] 所有 pytest 测试通过（6+）
- [ ] mypy 类型检查无错误
- [ ] ruff 代码风格检查无错误
