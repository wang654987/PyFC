# Vibecoding Prompt 01: Cartridge + Palette 基础模块

## 概述

实现 `cartridge.py`（ROM 加载 + Mapper 0）和 `palette.py`（FC 系统调色板）。这两个模块是项目中最基础的组件，不依赖其他项目模块，可以完全独立开发和测试。

## 前置条件

- Python 3.12+
- `pytest`, `mypy`, `ruff` 已安装（`uv pip install -e .[dev]`）
- 项目根目录有 `Super Mario Bros. (E) (PRG0) [!].nes` ROM 文件

## 你要创建/修改的文件

### 1. `src/cartridge.py` — ROM 加载与 Mapper 0

#### 1.1 iNES 文件头解析

iNES 文件头为 16 字节，结构如下：

```
Offset  Size  描述
0       4     魔数 "NES\x1A"（bytes: 0x4E 0x45 0x53 0x1A）
4       1     PRG-ROM 银行数（每个银行 16KB = 16384 字节）
5       1     CHR-ROM 银行数（每个银行 8KB = 8192 字节）
6       1     Flag 6:
                bit 0:  镜像模式（0=水平, 1=垂直）
                bit 2:  Trainer 存在标志
                bit 3:  SRAM 存在标志
                bits 4-7: Mapper 编号低 4 位
7       1     Flag 7:
                bits 4-7: Mapper 编号高 4 位
8-15    8     保留（通常为 0）
```

Mapper 编号计算：`mapper_id = (flag7 & 0xF0) | (flag6 >> 4)`

#### 1.2 Cartridge 类接口

```python
from __future__ import annotations

class Cartridge:
    """FC/NES 卡带模拟器，支持 Mapper 0 (NROM)。"""

    def __init__(self, rom_data: bytes) -> None:
        """
        从 bytes 数据解析 ROM（方便测试时直接构造数据，生产时可从文件读取）。

        Raises:
            ValueError: 如果 ROM 魔数不正确
        """
        ...

    # ---- 属性 ----
    prg_rom: bytearray       # PRG-ROM 数据
    chr_rom: bytearray       # CHR-ROM 数据
    mapper_id: int           # Mapper 编号
    mirror_mode: int         # 0=水平镜像, 1=垂直镜像
    prg_banks: int           # PRG-ROM 银行数
    chr_banks: int           # CHR-ROM 银行数

    # ---- Mapper 0 读取接口 ----
    def cpu_read(self, address: int) -> int:
        """
        CPU 侧读取 PRG-ROM（$8000-$FFFF）。

        Mapper 0 映射规则：
        - 1 个 16KB 银行 → 镜像到 $8000-$BFFF 和 $C000-$FFFF
        - 2 个 16KB 银行 → $8000-$BFFF = 银行0, $C000-$FFFF = 银行1

        如果 address < 0x8000，返回 0。
        """

    def cpu_write(self, address: int, value: int) -> None:
        """CPU 侧写入。Mapper 0 使用 ROM，忽略写入。"""

    def ppu_read(self, address: int) -> int:
        """
        PPU 侧读取 CHR-ROM（$0000-$1FFF）。

        如果 address >= 0x2000 或 CHR-ROM 为空，返回 0。
        """

    def ppu_write(self, address: int, value: int) -> None:
        """PPU 侧写入。Mapper 0 使用 CHR-ROM（只读），忽略写入。"""
```

#### 1.3 Trainer 处理

如果 Flag 6 的 bit 2 为 1，则头部后 512 字节为 Trainer（非标准数据），需要跳过。

#### 1.4 重要实现细节

- 构造函数接受 `bytes`（不是文件路径），方便单元测试
- PRG-ROM 大小 = `prg_banks * 16384`
- CHR-ROM 大小 = `chr_banks * 8192`（可能为 0，表示使用 CHR-RAM）
- `cpu_read` 中地址 mod PRG-ROM 大小处理映射
- 使用 `bytearray` 存储 ROM 数据（与 RAM 一致）

### 2. `src/palette.py` — FC 系统调色板

#### 2.1 64 色 RGB 映射表

```python
"""FC/NES 系统调色板 — 64 色 RGB 值映射表。

索引 0-63，每个值格式为 0xRRGGBB。
"""

PALETTE: list[int] = [
    0x666666, 0x002A88, 0x1412A7, 0x3B00A4,
    0x5C007E, 0x6E0040, 0x6C0600, 0x561D00,
    0x333400, 0x0B4800, 0x005200, 0x004F08,
    0x00404D, 0x000000, 0x000000, 0x000000,
    0xADADAD, 0x155FD9, 0x4240FF, 0x7527FE,
    0xA01ACC, 0xB71E7B, 0xB53120, 0x994E00,
    0x6B6D00, 0x388700, 0x0C9300, 0x008F32,
    0x007C8D, 0x000000, 0x000000, 0x000000,
    0xFFFEFF, 0x64B0FF, 0x9290FF, 0xC676FF,
    0xF36AFF, 0xFE6ECC, 0xFE8170, 0xEA9E22,
    0xBCBE00, 0x88D800, 0x5CE430, 0x45E082,
    0x48CEDE, 0x4F4F4F, 0x000000, 0x000000,
    0xFFFEFF, 0xC0DFFF, 0xD3D2FF, 0xE8C8FF,
    0xFBC2FF, 0xFEC4EA, 0xFECCC5, 0xF7D8A5,
    0xE4E594, 0xCFEF96, 0xBDF4AB, 0xB3F3CC,
    0xB5EBF2, 0xB8B8B8, 0x000000, 0x000000,
]
```

共 64 个值。注意列表中的 0x000000 是占位符（FC 调色板中某些索引未定义）。

#### 2.2 工具函数

```python
def get_color(palette_index: int) -> int:
    """根据调色板索引（0-63）返回 RGB 颜色值。"""
    return PALETTE[palette_index & 0x3F]
```

## 测试要求

### `tests/test_cartridge.py`

至少包含以下测试用例：

1. **test_valid_ines_header** — 构造合法的 iNES 头部，验证解析结果
2. **test_invalid_magic_number** — 非法魔数应抛出 ValueError
3. **test_mapper_id_parsing** — 验证 Mapper 编号正确计算
4. **test_mirror_mode** — 验证水平/垂直镜像标志
5. **test_cpu_read_prg_rom** — 测试 PRG-ROM 读取（单银行和双银行）
6. **test_ppu_read_chr_rom** — 测试 CHR-ROM 读取
7. **test_load_real_rom** — 加载超级玛丽 ROM 文件，验证 mapper_id=0, prg_banks=2, chr_banks=1
8. **test_trainer_skip** — 构造带 Trainer 的 ROM，验证跳过正确

### `tests/test_palette.py`

至少包含以下测试用例：

1. **test_palette_size** — 验证 PALETTE 有 64 个元素
2. **test_get_color** — 验证 get_color(0) 返回 0x666666
3. **test_get_color_wrap** — 验证 get_color(64) 等价于 get_color(0)（位掩码）
4. **test_palette_all_valid_rgb** — 验证所有值都是有效的 0xRRGGBB 格式

## 质量检查

开发完成后，必须通过以下检查：

```bash
# 1. ruff 代码风格检查
ruff check src/cartridge.py src/palette.py tests/test_cartridge.py tests/test_palette.py

# 2. mypy 类型检查
mypy src/cartridge.py src/palette.py

# 3. pytest 单元测试（必须全部通过）
pytest tests/test_cartridge.py tests/test_palette.py -v
```

## 与其他模块的接口

你的模块被以下模块依赖：

| 被依赖模块 | 使用方式 |
|-----------|---------|
| `bus.py` | 调用 `cartridge.cpu_read(addr)` / `cartridge.cpu_write(addr, val)` |
| `ppu_bus.py` | 调用 `cartridge.ppu_read(addr)` / `cartridge.ppu_write(addr, val)` |
| `ppu.py` | 调用 `get_color(index)` 获取 RGB 颜色 |

你**不需要**关心这些模块的实现，只需要确保你提供的公开接口符合规范。

## 文件清单

```
src/cartridge.py          # ← 创建
src/palette.py            # ← 创建
tests/test_cartridge.py   # ← 创建
tests/test_palette.py     # ← 创建
```

## 验收标准

- [ ] 能正确解析超级玛丽 ROM 文件（`mapper_id=0, prg_banks=2, chr_banks=1`）
- [ ] Mapper 0 CPU/PPU 读写逻辑正确
- [ ] 调色板 64 色数据完整且正确
- [ ] 所有 pytest 测试通过
- [ ] mypy 类型检查无错误
- [ ] ruff 代码风格检查无错误
