"""Controller 单元测试.

测试 FC 手柄控制器的按钮状态、锁存协议、串行读取和键位映射。
"""

from __future__ import annotations

from src.input import Controller


class TestButtonState:
    """按钮状态测试."""

    def test_button_constants(self) -> None:
        """验证所有按钮常量唯一且范围正确（0-7）."""
        buttons = [
            Controller.BUTTON_A,
            Controller.BUTTON_B,
            Controller.BUTTON_SELECT,
            Controller.BUTTON_START,
            Controller.BUTTON_UP,
            Controller.BUTTON_DOWN,
            Controller.BUTTON_LEFT,
            Controller.BUTTON_RIGHT,
        ]
        # 范围正确
        for b in buttons:
            assert 0 <= b <= 7
        # 全部唯一
        assert len(set(buttons)) == 8

    def test_key_press_sets_bit(self) -> None:
        """按下 'w' 设置 bit 4（UP）."""
        ctrl = Controller()
        ctrl.key_press("w")
        assert ctrl.button_state == (1 << Controller.BUTTON_UP)
        assert ctrl.button_state & (1 << Controller.BUTTON_UP) != 0

    def test_key_release_clears_bit(self) -> None:
        """释放 'w' 清除 bit 4."""
        ctrl = Controller()
        ctrl.key_press("w")
        assert ctrl.button_state & (1 << Controller.BUTTON_UP) != 0
        ctrl.key_release("w")
        assert ctrl.button_state == 0

    def test_multiple_buttons_pressed(self) -> None:
        """同时按下 A + Start，bits 0 和 3 都设置."""
        ctrl = Controller()
        ctrl.key_press("j")  # A
        ctrl.key_press("Return")  # Start
        expected = (1 << Controller.BUTTON_A) | (1 << Controller.BUTTON_START)
        assert ctrl.button_state == expected

    def test_key_release_only_affects_one_button(self) -> None:
        """释放不影响其他按钮."""
        ctrl = Controller()
        ctrl.key_press("w")  # Up
        ctrl.key_press("a")  # Left
        ctrl.key_release("w")  # 只释放 Up
        # Left 仍应保持按下
        assert ctrl.button_state & (1 << Controller.BUTTON_LEFT) != 0
        # Up 应已释放
        assert ctrl.button_state & (1 << Controller.BUTTON_UP) == 0

    def test_unknown_key_ignored(self) -> None:
        """按未映射的键不改变 button_state."""
        ctrl = Controller()
        ctrl.key_press("F1")  # 未映射
        assert ctrl.button_state == 0
        ctrl.key_release("F1")  # 释放未映射的键也不影响
        assert ctrl.button_state == 0

    def test_key_press_toggle(self) -> None:
        """按下→释放→按下 的正确状态变化."""
        ctrl = Controller()
        # 按下
        ctrl.key_press("k")  # B
        assert ctrl.button_state & (1 << Controller.BUTTON_B) != 0
        # 释放
        ctrl.key_release("k")
        assert ctrl.button_state == 0
        # 再次按下
        ctrl.key_press("k")
        assert ctrl.button_state & (1 << Controller.BUTTON_B) != 0


class TestLatchProtocol:
    """锁存协议测试."""

    def test_strobe_write_1(self) -> None:
        """写入 1 进入锁存模式."""
        ctrl = Controller()
        ctrl.key_press("j")  # 按下 A
        ctrl.write(1)
        # 进入锁存模式
        assert ctrl._strobe is True
        # 移位寄存器捕获了当前按钮状态
        assert ctrl._shift_register == ctrl.button_state
        # 读取计数重置为 0
        assert ctrl._read_count == 0

    def test_strobe_write_0(self) -> None:
        """写入 0 退出锁存模式."""
        ctrl = Controller()
        ctrl.write(1)  # 进入锁存
        assert ctrl._strobe is True
        ctrl.write(0)  # 退出锁存
        assert ctrl._strobe is False

    def test_read_during_strobe(self) -> None:
        """锁存期间读取返回 A 按钮状态."""
        ctrl = Controller()
        ctrl.key_press("j")  # 按下 A
        ctrl.write(1)  # 进入锁存
        assert ctrl.read() == 1  # A 按下，返回 1

        ctrl.key_release("j")  # 释放 A
        assert ctrl.read() == 0  # A 释放，返回 0


class TestSerialRead:
    """串行读取测试."""

    def test_serial_read_order(self) -> None:
        """验证读取顺序 A→B→Select→Start→Up→Down→Left→Right."""
        # 每个按钮单独测试，验证其在序列中的正确位置
        test_cases: list[tuple[str, int]] = [
            ("j", 0),  # A
            ("k", 1),  # B
            ("Shift_R", 2),  # Select
            ("Return", 3),  # Start
            ("w", 4),  # Up
            ("s", 5),  # Down
            ("a", 6),  # Left
            ("d", 7),  # Right
        ]
        for key, expected_pos in test_cases:
            ctrl = Controller()
            ctrl.key_press(key)
            ctrl.write(1)  # 锁存
            ctrl.write(0)  # 开始读取
            results = [ctrl.read() for _ in range(8)]
            for i, val in enumerate(results):
                if i == expected_pos:
                    assert val == 1, f"key={key}: 位置 {i} 应为 1, 得到 {results}"
                else:
                    assert val == 0, f"key={key}: 位置 {i} 应为 0, 得到 {results}"

    def test_serial_read_all_buttons(self) -> None:
        """设置所有按钮，连续读 8 次返回全 1."""
        ctrl = Controller()
        for key in ["j", "k", "Shift_R", "Return", "w", "s", "a", "d"]:
            ctrl.key_press(key)
        ctrl.write(1)
        ctrl.write(0)
        results = [ctrl.read() for _ in range(8)]
        assert results == [1, 1, 1, 1, 1, 1, 1, 1]

    def test_serial_read_no_buttons(self) -> None:
        """无按钮按下，读 8 次返回全 0."""
        ctrl = Controller()
        ctrl.write(1)
        ctrl.write(0)
        results = [ctrl.read() for _ in range(8)]
        assert results == [0, 0, 0, 0, 0, 0, 0, 0]

    def test_read_beyond_eight(self) -> None:
        """第 9 次及以后读取返回 1."""
        ctrl = Controller()
        ctrl.write(1)
        ctrl.write(0)
        # 前 8 次读取
        for _ in range(8):
            ctrl.read()
        # 第 9 次及以后应返回 1
        for _ in range(10):
            assert ctrl.read() == 1

    def test_read_mixed_buttons(self) -> None:
        """按下 A+Up+Start，验证只有对应位为 1."""
        ctrl = Controller()
        ctrl.key_press("j")  # A (bit 0)
        ctrl.key_press("w")  # Up (bit 4)
        ctrl.key_press("Return")  # Start (bit 3)
        ctrl.write(1)
        ctrl.write(0)
        results = [ctrl.read() for _ in range(8)]
        # bit 0 (A)=1, bit 1 (B)=0, bit 2 (Select)=0, bit 3 (Start)=1,
        # bit 4 (Up)=1, bit 5 (Down)=0, bit 6 (Left)=0, bit 7 (Right)=0
        assert results == [1, 0, 0, 1, 1, 0, 0, 0]


class TestCompleteSequence:
    """完整序列测试."""

    def test_full_strobe_read_sequence(self) -> None:
        """完整的锁存→读取 8 次→再锁存序列."""
        ctrl = Controller()
        # 第一次：按下 A 和 B
        ctrl.key_press("j")  # A
        ctrl.key_press("k")  # B
        ctrl.write(1)
        ctrl.write(0)
        first_read = [ctrl.read() for _ in range(8)]
        assert first_read == [1, 1, 0, 0, 0, 0, 0, 0]

        # 改变按钮状态：释放 B，按下 Start
        ctrl.key_release("k")
        ctrl.key_press("Return")  # Start
        ctrl.write(1)
        ctrl.write(0)
        second_read = [ctrl.read() for _ in range(8)]
        assert second_read == [1, 0, 0, 1, 0, 0, 0, 0]

    def test_strobe_relatch_mid_read(self) -> None:
        """读取到一半再锁存，重新开始."""
        ctrl = Controller()
        ctrl.key_press("j")  # A
        ctrl.write(1)
        ctrl.write(0)
        # 读取前 3 位
        ctrl.read()  # A
        ctrl.read()  # B
        ctrl.read()  # Select
        # 再次锁存（重新捕获状态，重置读取位置）
        ctrl.write(1)
        ctrl.write(0)
        # 重新从头读取
        results = [ctrl.read() for _ in range(8)]
        # 只有 A 按下
        assert results == [1, 0, 0, 0, 0, 0, 0, 0]

    def test_reset(self) -> None:
        """reset() 后所有状态归零."""
        ctrl = Controller()
        ctrl.key_press("j")
        ctrl.key_press("w")
        ctrl.write(1)
        ctrl.write(0)
        for _ in range(3):
            ctrl.read()
        # 确认状态非零
        assert ctrl.button_state != 0
        assert ctrl._read_count != 0

        ctrl.reset()
        assert ctrl.button_state == 0
        assert ctrl._strobe is False
        assert ctrl._shift_register == 0
        assert ctrl._read_count == 0


class TestKeyMap:
    """键位映射测试."""

    def test_key_map_has_all_buttons(self) -> None:
        """验证 KEY_MAP 覆盖所有 8 个按钮."""
        mapped_buttons = set(Controller.KEY_MAP.values())
        expected_buttons = set(range(8))
        assert mapped_buttons == expected_buttons

    def test_key_map_aliases(self) -> None:
        """验证备选键位（如 'z' 也是 A, 'x' 也是 B）."""
        ctrl = Controller()
        # 主键位 A
        ctrl.key_press("j")
        assert ctrl.button_state & (1 << Controller.BUTTON_A) != 0
        ctrl.reset()
        # 备选键位 A
        ctrl.key_press("z")
        assert ctrl.button_state & (1 << Controller.BUTTON_A) != 0
        ctrl.reset()
        # 主键位 B
        ctrl.key_press("k")
        assert ctrl.button_state & (1 << Controller.BUTTON_B) != 0
        ctrl.reset()
        # 备选键位 B
        ctrl.key_press("x")
        assert ctrl.button_state & (1 << Controller.BUTTON_B) != 0


class TestAdditional:
    """额外边界测试."""

    def test_initial_state(self) -> None:
        """验证初始化状态全部正确归零."""
        ctrl = Controller()
        assert ctrl.button_state == 0
        assert ctrl._strobe is False
        assert ctrl._shift_register == 0
        assert ctrl._read_count == 0

    def test_strobe_updates_shift_register(self) -> None:
        """锁存时捕获最新的 button_state."""
        ctrl = Controller()
        # 第一次锁存：无按钮按下
        ctrl.write(1)
        assert ctrl._shift_register == 0
        ctrl.write(0)

        # 按下按钮后再次锁存
        ctrl.key_press("d")  # Right (bit 7)
        ctrl.write(1)
        assert ctrl._shift_register == (1 << 7)
        ctrl.write(0)
        results = [ctrl.read() for _ in range(8)]
        assert results[7] == 1

    def test_write_ignores_high_bits(self) -> None:
        """write() 只使用 bit 0 判断锁存."""
        ctrl = Controller()
        ctrl.key_press("j")  # A
        # 写入 3（bit 0 = 1），应触发锁存
        ctrl.write(3)
        assert ctrl._strobe is True
        assert ctrl._shift_register == ctrl.button_state

        # 写入 2（bit 0 = 0），应退出锁存
        ctrl.write(2)
        assert ctrl._strobe is False

    def test_direction_key_aliases(self) -> None:
        """方向键同时支持字母键（wasd）和方向键（Up/Down/Left/Right）."""
        ctrl = Controller()
        # WASD 字母键
        ctrl.key_press("w")
        assert ctrl.button_state & (1 << Controller.BUTTON_UP) != 0
        ctrl.reset()
        # 方向键
        ctrl.key_press("Up")
        assert ctrl.button_state & (1 << Controller.BUTTON_UP) != 0

        ctrl.reset()
        ctrl.key_press("Down")
        assert ctrl.button_state & (1 << Controller.BUTTON_DOWN) != 0

        ctrl.reset()
        ctrl.key_press("Left")
        assert ctrl.button_state & (1 << Controller.BUTTON_LEFT) != 0

        ctrl.reset()
        ctrl.key_press("Right")
        assert ctrl.button_state & (1 << Controller.BUTTON_RIGHT) != 0

    def test_read_during_strobe_does_not_advance(self) -> None:
        """锁存期间多次读取始终返回 A 状态，不推进读取位置."""
        ctrl = Controller()
        ctrl.key_press("j")  # A 按下
        ctrl.write(1)
        # 锁存期间多次读取，始终返回 A 的当前状态
        assert ctrl.read() == 1
        assert ctrl.read() == 1
        assert ctrl.read() == 1
        # 释放 A，锁存期间的读取反映最新的 A 状态
        ctrl.key_release("j")
        assert ctrl.read() == 0
        # 退出锁存，开始正常读取
        # 注意：shift_register 是在 write(1) 时锁存的，当时 A 按下，所以 bit 0=1
        ctrl.write(0)
        results = [ctrl.read() for _ in range(8)]
        # 锁存时 A 是按下状态，所以第一位为 1，其余为 0
        assert results == [1, 0, 0, 0, 0, 0, 0, 0]
