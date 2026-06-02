# Vibecoding Prompts 目录

本目录包含 7 个独立的 vibecoding prompt 文件，每个对应一组可以独立开发、独立测试的模块。

## Prompt 文件索引

| # | 文件 | 模块 | 依赖 | Wave |
|---|------|------|------|------|
| 01 | [01-cartridge-palette.md](01-cartridge-palette.md) | `cartridge.py` `palette.py` | 无 | Wave 1 |
| 02 | [02-cpu-core.md](02-cpu-core.md) | `cpu.py` | Bus 接口(用 Stub) | Wave 1 |
| 03 | [03-bus-system.md](03-bus-system.md) | `bus.py` `ppu_bus.py` | Cartridge/PPU/Controller 接口(用 Mock) | Wave 2 |
| 04 | [04-ppu-core.md](04-ppu-core.md) | `ppu.py` | PPUBus 接口(用 Mock) | Wave 2 |
| 05 | [05-input-controller.md](05-input-controller.md) | `input.py` | 无 | Wave 1 |
| 06 | [06-renderer.md](06-renderer.md) | `renderer.py` | Controller 接口 + Tkinter | Wave 2 |
| 07 | [07-emulator-main.md](07-emulator-main.md) | `emulator.py` `main.py` | 所有模块 | Wave 3 |

## 执行计划

### Wave 1（并行 3 Agent，互不冲突）
- Agent A → Prompt 01：`src/cartridge.py` + `src/palette.py` + 测试
- Agent B → Prompt 02：`src/cpu.py` + 测试
- Agent C → Prompt 05：`src/input.py` + 测试

### Wave 2（并行 3 Agent，互不冲突，依赖 Wave 1 接口）
- Agent D → Prompt 03：`src/bus.py` + `src/ppu_bus.py` + 测试
- Agent E → Prompt 04：`src/ppu.py` + 测试
- Agent F → Prompt 06：`src/renderer.py` + 测试

### Wave 3（1 Agent，依赖 Wave 1+2）
- Agent G → Prompt 07：`src/emulator.py` + `src/main.py` + 集成测试

## 质量要求

每个 Agent 完成后必须通过：
- `ruff check` — 代码风格
- `mypy` — 类型检查
- `pytest -v` — 所有单元测试通过（覆盖率 100%）
