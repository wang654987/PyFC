# Vibecoding Prompt 05: 输入控制器模块

## 概述

实现 `Controller` 类，模拟 FC 手柄的串行读取协议。这个模块完全独立，不依赖其他项目模块，非常容易测试。

## 前置条件

- 无内部依赖，只需 Python 标准库

## FC 手柄协议背景

FC 手柄有 8 个按钮，通过 `$4016` 端口以串行方式读取：

1. CPU 向 `$4016` 写入 `1` 然后写入 `0`，锁存当前按钮状态
2. CPU 连续读取 `$4016` 8 次，每次返回一个按钮的状态（按 A→B→Select→Start→Up→Down→Left→Right 的顺序）
3. 第 9 次及之后读取返回 `1`

## 你要创建/修改的文件

### `src/input.py` — 手柄控制器

#### Controller 类完整实现

```python
from __future__ import annotations

class Controller:
    """FC/NES 手柄控制器模拟。

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
    KEY_MAP: dict[str, int] = {
        # WASD 方向
        "w": 4,          # Up
        "s": 5,          # Down
        "a": 6,          # Left
        "d": 7,          # Right
        # 方向键
        "Up": 4,
        "Down": 5,
        "Left": 6,
        "Right": 7,
        # 动作按钮
        "j": 0,          # A
        "z": 0,          # A（备选）
        "k": 1,          # B
        "x": 1,          # B（备选）
        # 功能按钮
        "Return": 3,     # Start
        "Shift_R": 2,    # Select
    }

    def __init__(self) -> None:
        # button_state: 8 位位掩码，bit 0=A, bit 1=B, ..., bit 7=Right
        # 1 = 按下，0 = 释放
        self.button_state: int = 0
        self._strobe: bool = False
        self._shift_register: int = 0
        self._read_count: int = 0

    def write(self, value: int) -> None:
        """
        写入 $4016 端口。

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
        """
        读取 $4016 端口。

        Returns:
            当前位的按钮状态（0 或 1）

        行为：
        - 锁存期间（strobe=1）：始终返回 A 按钮状态（button_state bit 0）
        - 正常读取：返回 shift_register 的最低位，然后右移一位
        - 超过 8 次读取后：返回 1（FC 标准行为）
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
        """
        键盘按下事件处理。

        如果按键在 KEY_MAP 中，设置对应的按钮位为 1。

        Args:
            key: Tkinter 事件 keysym（如 "w", "Up", "Return"）
        """
        if key in self.KEY_MAP:
            self.button_state |= (1 << self.KEY_MAP[key])

    def key_release(self, key: str) -> None:
        """
        键盘释放事件处理。

        如果按键在 KEY_MAP 中，清除对应的按钮位。

        Args:
            key: Tkinter 事件 keysym
        """
        if key in self.KEY_MAP:
            self.button_state &= ~(1 << self.KEY_MAP[key])

    def reset(self) -> None:
        """重置控制器状态。"""
        self.button_state = 0
        self._strobe = False
        self._shift_register = 0
        self._read_count = 0
```

## 测试要求

### `tests/test_input.py`

至少包含以下测试：

**按钮状态测试**：
1. `test_button_constants` — 验证所有按钮常量唯一且范围正确（0-7）
2. `test_key_press_sets_bit` — 按下 'w' 设置 bit 4（UP）
3. `test_key_release_clears_bit` — 释放 'w' 清除 bit 4
4. `test_multiple_buttons_pressed` — 同时按下 A + Start → bits 0 和 3 都设置
5. `test_key_release_only_affects_one_button` — 释放不影响其他按钮
6. `test_unknown_key_ignored` — 按未映射的键不改变 button_state
7. `test_key_press_toggle` — 按下→释放→按下 的正确状态变化

**锁存协议测试**：
8. `test_strobe_write_1` — 写入 1 进入锁存模式
9. `test_strobe_write_0` — 写入 0 退出锁存模式
10. `test_read_during_strobe` — 锁存期间读取返回 A 按钮状态

**串行读取测试**：
11. `test_serial_read_order` — 验证读取顺序 A→B→Select→Start→Up→Down→Left→Right
12. `test_serial_read_all_buttons` — 设置所有按钮，连续读 8 次返回全 1
13. `test_serial_read_no_buttons` — 无按钮按下，读 8 次返回全 0
14. `test_read_beyond_eight` — 第 9 次及以后读取返回 1
15. `test_read_mixed_buttons` — 按下 A+Up+Start，验证只有对应位为 1

**完整序列测试**：
16. `test_full_strobe_read_sequence` — 完整的锁存→读取 8 次→再锁存序列
17. `test_strobe_relatch_mid_read` — 读取到一半再锁存，重新开始
18. `test_reset` — reset() 后所有状态归零

**键位映射测试**：
19. `test_key_map_has_all_buttons` — 验证 KEY_MAP 覆盖所有 8 个按钮
20. `test_key_map_aliases` — 验证备选键位（如 'z' 也是 A, 'x' 也是 B）

## 质量检查

```bash
# 1. ruff 代码风格检查
ruff check src/input.py tests/test_input.py

# 2. mypy 类型检查
mypy src/input.py

# 3. pytest 单元测试
pytest tests/test_input.py -v
```

## 与其他模块的接口

| 被依赖模块 | 使用方式 |
|-----------|---------|
| `bus.py` | 通过 `controller.write(val)` 处理 $4016 写入；通过 `controller.read()` 处理 $4016 读取 |
| `renderer.py` | 调用 `controller.key_press(keysym)` / `controller.key_release(keysym)` 处理键盘事件 |
| `emulator.py` | 创建 Controller 实例并传递给 Bus 和 Renderer |

## 文件清单

```
src/input.py              # ← 创建
tests/test_input.py       # ← 创建
```

## 验收标准

- [ ] 8 个按钮常量正确定义
- [ ] 键位映射表完整（WASD + 方向键 + J/Z + K/X + Enter + Right Shift）
- [ ] 手柄锁存协议正确（strobe 1→0 序列）
- [ ] 串行读取顺序正确（A→B→Select→Start→Up→Down→Left→Right）
- [ ] 第 9 次及以后读取返回 1
- [ ] 所有 pytest 测试通过（20+）
- [ ] mypy 类型检查无错误
- [ ] ruff 代码风格检查无错误
