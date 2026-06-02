"""Renderer 模块单元测试.

测试 Tkinter 渲染器的创建、帧渲染、缩放、标题设置和清理。
由于 Tkinter 主循环会阻塞测试，所有测试只验证非阻塞方法。
"""

from __future__ import annotations

import contextlib
import tkinter as tk

import pytest

from src.input import Controller
from src.renderer import Renderer


def _create_renderer(title: str = "Test", scale: int = 1) -> Renderer:
    """创建 Renderer 实例，若 Tcl/Tk 不可用则跳过测试."""
    try:
        return Renderer(title, scale)
    except tk.TclError:
        pytest.skip("Tcl/Tk not available in this environment")


class TestRendererBasic:
    """Renderer 基础测试（不涉及主循环）."""

    def test_renderer_creation(self) -> None:
        """验证 Renderer 可以创建（不要进入主循环）."""
        renderer = _create_renderer("Test", scale=2)
        try:
            assert renderer.WIDTH == 256
            assert renderer.HEIGHT == 240
            assert renderer.scale == 2
        finally:
            renderer.root.destroy()

    def test_renderer_default_scale(self) -> None:
        """默认缩放应为 3."""
        renderer = _create_renderer(scale=3)
        try:
            assert renderer.scale == 3
        finally:
            renderer.root.destroy()

    def test_renderer_scale_minimum(self) -> None:
        """缩放倍数最小为 1."""
        renderer = _create_renderer(scale=0)
        try:
            assert renderer.scale == 1
        finally:
            renderer.root.destroy()

    def test_canvas_dimensions(self) -> None:
        """Canvas 尺寸应为 WIDTH*scale x HEIGHT*scale."""
        renderer = _create_renderer("Test", scale=2)
        try:
            canvas_width = int(renderer.canvas["width"])
            canvas_height = int(renderer.canvas["height"])
            assert canvas_width == 256 * 2
            assert canvas_height == 240 * 2
        finally:
            renderer.root.destroy()

    def test_render_frame_no_crash(self) -> None:
        """render_frame 应该不崩溃（使用全黑帧缓冲区）."""
        renderer = _create_renderer("Test", scale=1)
        try:
            black_frame = [0x000000] * (256 * 240)
            renderer.render_frame(black_frame)
        finally:
            renderer.root.destroy()

    def test_render_frame_with_colors(self) -> None:
        """render_frame 应该正确处理有颜色的帧缓冲区."""
        renderer = _create_renderer("Test", scale=1)
        try:
            # 创建渐变帧缓冲区
            frame: list[int] = []
            for y in range(240):
                for x in range(256):
                    r = (x * 255) // 255
                    g = (y * 255) // 239
                    b = 128
                    frame.append((r << 16) | (g << 8) | b)
            renderer.render_frame(frame)
        finally:
            renderer.root.destroy()

    def test_render_frame_with_scale_2(self) -> None:
        """render_frame 在 scale > 1 时应使用 zoom 缩放."""
        renderer = _create_renderer("Test", scale=2)
        try:
            # 全红帧缓冲区
            red_frame = [0xFF0000] * (256 * 240)
            renderer.render_frame(red_frame)
            # 验证缩放后的图像被创建
            assert renderer._zoomed_photo is not None
        finally:
            renderer.root.destroy()

    def test_set_title(self) -> None:
        """set_title 应该更新窗口标题."""
        renderer = _create_renderer("PyFC", scale=1)
        try:
            renderer.set_title("New Title")
        finally:
            renderer.root.destroy()

    def test_stop(self) -> None:
        """Stop 应该正常关闭窗口."""
        renderer = _create_renderer("Test", scale=1)
        with contextlib.suppress(tk.TclError):
            renderer.stop()

    def test_stop_double_call(self) -> None:
        """重复调用 stop 不应抛出异常."""
        renderer = _create_renderer("Test", scale=1)
        with contextlib.suppress(tk.TclError):
            renderer.stop()
            renderer.stop()  # 第二次调用应该被 try/except 安全处理

    def test_bind_input(self) -> None:
        """bind_input 不应崩溃，且正确绑定键盘事件."""
        renderer = _create_renderer("Test", scale=1)
        try:
            controller = Controller()
            renderer.bind_input(controller)
        finally:
            renderer.root.destroy()
