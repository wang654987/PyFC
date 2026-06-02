# Vibecoding Prompt 03: Bus + PPUBus 总线系统

## 概述

实现 `bus.py`（CPU 地址空间）和 `ppu_bus.py`（PPU 地址空间）两个总线模块。两个模块都是**纯路由器**，不持有设备状态，只负责地址解码和数据转发。

## 前置条件

- `src/cartridge.py` 的 Cartridge 类接口已定义（`cpu_read`, `cpu_write`, `ppu_read`, `ppu_write`）
- 你的测试不需要真实的 Cartridge 实例 — 使用 Mock 替身

## 你要创建/修改的文件

### 1. `src/bus.py` — CPU 总线（地址空间 $0000-$FFFF）

#### 1.1 Bus 类设计

Bus 是一个纯路由器，所有外部设备通过构造函数注入：

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cpu import CPU6502
    from .ppu import PPU
    from .cartridge import Cartridge
    from .input import Controller

class Bus:
    """CPU 总线 — 管理 64KB 地址空间。"""

    def __init__(
        self,
        ram: bytearray | None = None,
        ppu: PPU | None = None,
        cartridge: Cartridge | None = None,
        controller: Controller | None = None,
    ) -> None:
        """各组件可为 None（测试时部分注入）。"""
        self.ram: bytearray = ram if ram is not None else bytearray(2048)
        self.ppu: PPU | None = ppu
        self.cartridge: Cartridge | None = cartridge
        self.controller: Controller | None = controller
```

#### 1.2 地址映射逻辑

```python
def read(self, address: int) -> int:
    """
    从指定 CPU 地址读取一个字节。

    地址解码：
    - $0000-$1FFF → RAM（2KB 镜像到 8KB，使用 & 0x07FF 掩码）
    - $2000-$3FFF → PPU 寄存器（8 字节镜像，使用 & 0x07 掩码）
    - $4000-$4015 → APU 寄存器（暂返回 0）
    - $4016        → 手柄 1 读取
    - $4017        → 手柄 2 读取（暂返回 0）
    - $4018-$401F → APU 测试寄存器（暂返回 0）
    - $4020-$FFFF → 卡带 PRG-ROM 空间
    """
    address &= 0xFFFF

    if address < 0x2000:
        return self.ram[address & 0x07FF]

    if address < 0x4000:
        if self.ppu is not None:
            return self.ppu.cpu_read(0x2000 + (address & 0x07))
        return 0

    if address == 0x4016:
        if self.controller is not None:
            return self.controller.read()
        return 0

    if address == 0x4017:
        return 0  # 手柄2暂不实现

    if address >= 0x4020:
        if self.cartridge is not None:
            return self.cartridge.cpu_read(address)
        return 0

    return 0  # APU 区域

def write(self, address: int, value: int) -> None:
    """
    向指定 CPU 地址写入一个字节。

    地址解码同 read()。

    特殊操作：
    - $4014: OAM DMA — 将 CPU 内存的 256 字节复制到 PPU OAM
    - $4016: 手柄控制写入
    """
    address &= 0xFFFF
    value &= 0xFF

    if address < 0x2000:
        self.ram[address & 0x07FF] = value
        return

    if address < 0x4000:
        if self.ppu is not None:
            self.ppu.cpu_write(0x2000 + (address & 0x07), value)
        return

    if address == 0x4014:
        # OAM DMA: 将内存页 (value << 8) 的 256 字节复制到 PPU OAM
        if self.ppu is not None:
            base_addr = value << 8
            for i in range(256):
                data = self.read(base_addr + i)
                self.ppu.oam_write(i, data)
        return

    if address == 0x4016:
        if self.controller is not None:
            self.controller.write(value)
        return

    if address >= 0x4020:
        if self.cartridge is not None:
            self.cartridge.cpu_write(address, value)
        return
```

#### 1.3 地址镜像说明

| 范围 | 物理大小 | 镜像次数 | 掩码 |
|------|---------|---------|------|
| RAM ($0000-$1FFF) | 2 KB | 4x → 8 KB | `addr & 0x07FF` |
| PPU Regs ($2000-$3FFF) | 8 B | 1024x → 8 KB | `addr & 0x07` |

### 2. `src/ppu_bus.py` — PPU 总线（地址空间 $0000-$3FFF）

#### 2.1 PPUBus 类设计

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cartridge import Cartridge

# 镜像模式常量
HORIZONTAL: int = 0
VERTICAL: int = 1

class PPUBus:
    """PPU 总线 — 管理 PPU 的 14 位地址空间。"""

    def __init__(
        self,
        cartridge: Cartridge | None = None,
        mirror_mode: int = HORIZONTAL,
    ) -> None:
        self.cartridge: Cartridge | None = cartridge
        self.nametable: bytearray = bytearray(2048)  # 2 KB
        self.mirror_mode: int = mirror_mode
```

#### 2.2 PPU 地址映射

```python
def read(self, address: int) -> int:
    """
    PPU 地址空间读取。

    - $0000-$1FFF → CHR-ROM（卡带提供）
    - $2000-$3EFF → Nametable（含镜像处理）
    - $3F00-$3FFF → 由 PPU 内部管理调色板（不经过 PPUBus）
    """
    address &= 0x3FFF

    if address < 0x2000:
        if self.cartridge is not None:
            return self.cartridge.ppu_read(address)
        return 0

    if address < 0x3F00:
        return self.nametable[self._mirror_address(address)]

    return 0  # 调色板由 PPU 管理

def write(self, address: int, value: int) -> None:
    """
    PPU 地址空间写入。

    - $0000-$1FFF → 通常为 CHR-ROM（只读），使用 CHR-RAM 时可写
    - $2000-$3EFF → Nametable 写入
    - $3F00-$3FFF → 由 PPU 内部管理
    """
    address &= 0x3FFF
    value &= 0xFF

    if address < 0x2000:
        if self.cartridge is not None:
            self.cartridge.ppu_write(address, value)
        return

    if address < 0x3F00:
        self.nametable[self._mirror_address(address)] = value
        return

    # 调色板区域由 PPU 管理，不经过 PPUBus

def _mirror_address(self, address: int) -> int:
    """
    Nametable 镜像处理。

    将 $2000-$3EFF 范围内的地址映射到 0-0xFFF（2KB 内）。

    水平镜像（默认）：
      $2000 = $2400, $2800 = $2C00
      即：table 0 = 0, table 1 = 0, table 2 = 1, table 3 = 1

    垂直镜像：
      $2000 = $2800, $2400 = $2C00
      即：table 0 = 0, table 1 = 1, table 2 = 0, table 3 = 1
    """
    addr = (address - 0x2000) & 0x0FFF  # 0-0xFFF
    table = addr // 0x0400  # 0, 1, 2, 3（哪张 Nametable）
    offset = addr % 0x0400  # 表内偏移

    if self.mirror_mode == VERTICAL:
        table &= 1  # 0→0, 1→1, 2→0, 3→1
    else:  # HORIZONTAL or default
        table = (table >> 1) & 1  # 0→0, 1→0, 2→1, 3→1

    return table * 0x0400 + offset
```

## 测试要求

### `tests/test_bus.py`

使用 Mock 对象测试：

```python
class MockPPU:
    def __init__(self):
        self.read_log: list[int] = []
        self.write_log: list[tuple[int, int]] = []
        self.oam_log: list[tuple[int, int]] = []

    def cpu_read(self, addr: int) -> int:
        self.read_log.append(addr)
        return 0x42

    def cpu_write(self, addr: int, value: int) -> None:
        self.write_log.append((addr, value))

    def oam_write(self, addr: int, value: int) -> None:
        self.oam_log.append((addr, value))
```

至少包含以下测试：

1. **test_ram_read_write** — 基本 RAM 读写
2. **test_ram_mirror_0800** — $0800 映射到 $0000
3. **test_ram_mirror_1000** — $1000 映射到 $0000
4. **test_ram_mirror_boundary** — $1FFF 映射到 $07FF
5. **test_ppu_register_read** — $2000 路由到 PPU
6. **test_ppu_register_mirror** — $3FF8 路由到 PPU $2000
7. **test_ppu_register_write** — $2001 写入路由到 PPU
8. **test_oam_dma** — 写入 $4014 触发 OAM DMA
9. **test_oam_dma_copies_256_bytes** — DMA 复制完整的 256 字节
10. **test_controller_read** — $4016 路由到 Controller
11. **test_cartridge_read** — $8000 路由到 Cartridge
12. **test_cartridge_write** — $8000 写入路由到 Cartridge
13. **test_apu_range_returns_zero** — $4000-$4015 返回 0
14. **test_write_value_clamped** — 写入值被截断到 8 位

### `tests/test_ppu_bus.py`

至少包含以下测试：

1. **test_chr_rom_read** — $0000 路由到 Cartridge
2. **test_nametable_read_write** — Nametable 基本读写
3. **test_horizontal_mirror** — 水平镜像：$2000 = $2400
4. **test_vertical_mirror** — 垂直镜像：$2000 = $2800
5. **test_nametable_mirror_boundary** — Nametable 镜像边界测试
6. **test_palette_area_returns_zero** — $3F00+ 从 PPUBus 返回 0（由 PPU 管理）

## 质量检查

```bash
# 1. ruff 代码风格检查
ruff check src/bus.py src/ppu_bus.py tests/test_bus.py tests/test_ppu_bus.py

# 2. mypy 类型检查
mypy src/bus.py src/ppu_bus.py

# 3. pytest 单元测试
pytest tests/test_bus.py tests/test_ppu_bus.py -v
```

## 与其他模块的接口

| 你的模块 | 被谁依赖 | 使用方式 |
|---------|---------|---------|
| `bus.py` | `cpu.py` | CPU 通过 `self.bus.read/write` 访问内存 |
| `bus.py` | `emulator.py` | Emulator 注入所有设备到 Bus |
| `ppu_bus.py` | `ppu.py` | PPU 通过 `self.ppu_bus.read/write` 访问 CHR-ROM 和 Nametable |
| `ppu_bus.py` | `emulator.py` | Emulator 创建 PPUBus 并注入 Cartridge |

## 文件清单

```
src/bus.py                # ← 创建
src/ppu_bus.py            # ← 创建
tests/test_bus.py         # ← 创建
tests/test_ppu_bus.py     # ← 创建
```

## 验收标准

- [ ] Bus 正确处理所有地址范围（RAM, PPU, APU, Controller, Cartridge）
- [ ] RAM 镜像正确（2KB → 8KB）
- [ ] PPU 寄存器镜像正确（8B → 8KB）
- [ ] OAM DMA 正确复制 256 字节
- [ ] PPUBus 正确处理 Nametable 镜像（水平/垂直）
- [ ] CHR-ROM 读写正确路由到 Cartridge
- [ ] 所有 pytest 测试通过
- [ ] mypy 类型检查无错误
- [ ] ruff 代码风格检查无错误
