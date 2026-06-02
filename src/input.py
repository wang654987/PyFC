"""FC/NES 手柄控制器模块.

提供 Controller 类，模拟 FC 手柄的串行读取协议。
"""

from __future__ import annotations


class Controller:
    """FC/NES 手柄控制器模拟.

    通过串行移位协议读取按钮状态。
    """

    # ---- 按钮常量 ----
    BUTTON_A: int = 0
    BUTTON_B: int = 1
    BUTTON_SELECT: int = 2
    BUTTON_START: int = 3
    BUTTON_UP: int = 4
    BUTTON_DOWN: int = 5
    BUTTON_LEFT: int = 6
    BUTTON_RIGHT: int = 7

    # ---- 键位映射（键盘按键 → FC 按钮索引）----
    # 同时支持 Tkinter keysym（首字母大写）和 Pygame key.name（全小写）
    KEY_MAP: dict[str, int] = {
        # WASD 方向（全小写 — Tkinter & Pygame 通用）
        "w": 4,  # Up
        "s": 5,  # Down
        "a": 6,  # Left
        "d": 7,  # Right
        # 方向键 — Tkinter 格式
        "Up": 4,
        "Down": 5,
        "Left": 6,
        "Right": 7,
        # 方向键 — Pygame 格式（全小写）
        "up": 4,
        "down": 5,
        "left": 6,
        "right": 7,
        # 动作按钮
        "j": 0,  # A
        "z": 0,  # A（备选）
        "k": 1,  # B
        "x": 1,  # B（备选）
        # 功能按钮 — Tkinter 格式
        "Return": 3,  # Start
        "Shift_R": 2,  # Select
        # 功能按钮 — Pygame 格式
        "return": 3,          # Start
        "right shift": 2,     # Select（右 Shift）
        "left shift": 2,      # Select（左 Shift 备选）
    }

    def __init__(self) -> None:
        """初始化控制器.

        所有按钮状态归零，锁存标志和读取计数清零。
        """
        # button_state: 8 位位掩码，bit 0=A, bit 1=B, ..., bit 7=Right
        # 1 = 按下，0 = 释放
        self.button_state: int = 0
        self._strobe: bool = False
        self._shift_register: int = 0
        self._read_count: int = 0

    def write(self, value: int) -> None:
        """写入 $4016 端口.

        协议：
        - 写入 1：设置锁存模式，冻结当前按钮状态到移位寄存器
        - 写入 0：退出锁存模式，开始串行读取

        Args:
            value: 写入值（只有 bit 0 有效）

        """
        self._strobe = bool(value & 1)
        if self._strobe:
            # 锁存：捕获当前按钮状态，重置读取位置
            self._shift_register = self.button_state
            self._read_count = 0
        # 当 strobe 从 1→0 时，shift_register 已就绪
        # 后续读取将从 bit 0 开始返回

    def read(self) -> int:
        """读取 $4016 端口.

        行为：
        - 锁存期间（strobe=1）：始终返回 A 按钮状态（button_state bit 0）
        - 正常读取：返回 shift_register 的最低位，然后右移一位
        - 超过 8 次读取后：返回 1（FC 标准行为）

        Returns:
            当前位的按钮状态（0 或 1）

        """
        if self._strobe:
            return self.button_state & 1

        if self._read_count < 8:
            result = self._shift_register & 1
            self._shift_register >>= 1
            self._read_count += 1
            return result
        else:
            # 超过 8 位后返回 1
            return 1

    def key_press(self, key: str) -> None:
        """键盘按下事件处理.

        如果按键在 KEY_MAP 中，设置对应的按钮位为 1。

        Args:
            key: Tkinter 事件 keysym（如 "w", "Up", "Return"）

        """
        if key in self.KEY_MAP:
            self.button_state |= 1 << self.KEY_MAP[key]

    def key_release(self, key: str) -> None:
        """键盘释放事件处理.

        如果按键在 KEY_MAP 中，清除对应的按钮位。

        Args:
            key: Tkinter 事件 keysym

        """
        if key in self.KEY_MAP:
            self.button_state &= ~(1 << self.KEY_MAP[key])

    def reset(self) -> None:
        """重置控制器状态."""
        self.button_state = 0
        self._strobe = False
        self._shift_register = 0
        self._read_count = 0
