"""FC/NES Tkinter 渲染器模块.

使用 Tkinter Canvas + PhotoImage 实现画面渲染。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .input import Controller


class Renderer:
    """Tkinter 渲染器 -- 负责画面显示和键盘事件处理.

    设计要点：
    - 使用 Tkinter Canvas 显示画面
    - 支持整数倍缩放（默认 3x）
    - 使用 PhotoImage 的 put() 方法批量写入像素（性能优化）
    - 键盘事件转发给 Controller
    """

    WIDTH: int = 256   # NES 原始宽度
    HEIGHT: int = 240  # NES 原始高度

    def __init__(self, title: str = "PyFC - FC Emulator", scale: int = 3) -> None:
        """初始化渲染窗口.

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
        self._zoomed_photo: tk.PhotoImage | None = None
        self._create_photo()

        self._running = False

    def _create_photo(self) -> None:
        """创建/重新创建 PhotoImage 对象."""
        self.canvas.delete("frame")
        self._photo = tk.PhotoImage(width=self.WIDTH, height=self.HEIGHT)
        self.canvas.create_image(
            0, 0,
            image=self._photo,
            anchor="nw",
            tags="frame",
        )

    def render_frame(self, framebuffer: list[int]) -> None:
        """将帧缓冲区渲染到 Canvas.

        Args:
            framebuffer: 长度为 256*240 的列表，每个元素是 0xRRGGBB 颜色值

        实现策略：
        - 使用颜色缓存避免重复的 f-string 格式化
        - 预分配字符串列表减少 append 开销
        - 使用 PhotoImage.put() 一次性写入整个图像

        """
        if self._photo is None:
            self._create_photo()
        assert self._photo is not None  # 类型收窄，消除 mypy union-attr 误报

        # 颜色字符串缓存：NES 游戏通常只使用少量颜色，避免重复格式化
        cache: dict[int, str] = {}
        rows: list[str] = [""] * self.HEIGHT

        for y in range(self.HEIGHT):
            row_start = y * self.WIDTH
            row_pixels: list[str] = [""] * self.WIDTH
            for x in range(self.WIDTH):
                rgb = framebuffer[row_start + x]
                s = cache.get(rgb)
                if s is None:
                    r = (rgb >> 16) & 0xFF
                    g = (rgb >> 8) & 0xFF
                    b = rgb & 0xFF
                    s = f"#{r:02x}{g:02x}{b:02x}"
                    cache[rgb] = s
                row_pixels[x] = s
            rows[y] = "{" + " ".join(row_pixels) + "}"

        self._photo.put(" ".join(rows))

        # 缩放处理
        if self.scale > 1:
            # 隐藏原始图像，显示缩放版本
            self.canvas.itemconfigure("frame", state="hidden")
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
        else:
            # scale == 1: 显示原始图像，清理缩放痕迹
            self.canvas.delete("scaled")
            self._zoomed_photo = None
            self.canvas.itemconfigure("frame", state="normal")

        self.canvas.update_idletasks()

    def bind_input(self, controller: Controller) -> None:
        """绑定键盘事件到控制器.

        绑定 <KeyPress> 和 <KeyRelease> 事件，
        转发给 controller.key_press() 和 controller.key_release().

        Args:
            controller: Controller 实例

        """
        def on_key_press(event: tk.Event[tk.Misc]) -> None:
            controller.key_press(event.keysym)

        def on_key_release(event: tk.Event[tk.Misc]) -> None:
            controller.key_release(event.keysym)

        self.root.bind("<KeyPress>", on_key_press)
        self.root.bind("<KeyRelease>", on_key_release)
        self.root.focus_set()

    def set_title(self, title: str) -> None:
        """更新窗口标题."""
        self.root.title(title)

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        """使用 Tkinter after() 定时调用回调.

        Args:
            delay_ms: 延迟毫秒数
            callback: 回调函数（无参数）

        """
        self.root.after(delay_ms, callback)

    def start(self) -> None:
        """启动 Tkinter 主循环（阻塞调用）."""
        self._running = True
        self.root.mainloop()

    def stop(self) -> None:
        """停止渲染器."""
        self._running = False
        try:
            self.root.quit()
            self.root.destroy()
        except tk.TclError:
            pass

    def update(self) -> None:
        """更新 Tkinter 事件循环（非阻塞）."""
        self.root.update()
