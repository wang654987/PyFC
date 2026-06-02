"""PPU (Picture Processing Unit) for the NES emulator.

Implements the complete PPU including register read/write, background
rendering, sprite rendering, scrolling, VBlank/NMI triggering, and
sprite-0 collision detection.

Address space:
    0x0000-0x1FFF  CHR-ROM (via PPUBus)
    0x2000-0x3EFF  Nametable + Attribute tables (via PPUBus)
    0x3F00-0x3F1F  Palette RAM (internal)
    0x3F20-0x3FFF  Palette mirror
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .palette import get_color

if TYPE_CHECKING:
    from collections.abc import Callable

    from .ppu_bus import PPUBus


class PPU:
    """NES PPU (Picture Processing Unit) emulator.

    Uses scanline-level rendering precision.  Each tick() advances one
    PPU cycle (3 PPU cycles = 1 CPU cycle).  Visible pixels are rendered
    per-cycle during active scanlines (0-239, cycles 0-255).

    Public attributes:
        framebuffer   -- flat list of 256×240 RGB colour values.
        frame_complete -- True once the current frame has been rendered.
        nmi_callback   -- callable invoked when the VBlank NMI fires.
        scanline       -- current scanline (0-261).
        cycle          -- current dot position within the scanline (0-340).
    """

    # ------------------------------------------------------------------
    #  Initialisation & reset
    # ------------------------------------------------------------------

    def __init__(self, ppu_bus: PPUBus) -> None:
        """Create a PPU wired to *ppu_bus* for CHR-ROM/Nametable access."""
        self.ppu_bus: PPUBus = ppu_bus

        # ---- PPU registers ($2000-$2007, CPU-facing) ----
        self.ctrl: int = 0       # $2000  PPUCTRL
        self.mask: int = 0       # $2001  PPUMASK
        self.status: int = 0     # $2002  PPUSTATUS
        self.oam_addr: int = 0   # $2003  OAMADDR
        self.oam_data: int = 0   # $2004  OAMDATA  (not used directly)
        self.scroll_x: int = 0   # $2005  first write
        self.scroll_y: int = 0   # $2005  second write
        self.vram_addr: int = 0  # $2006  current 14-bit VRAM address
        self.read_buffer: int = 0  # $2007  pre-read buffer

        # ---- Internal latches ----
        self._write_latch: bool = False  # True → waiting for second write
        self._scroll_x: int = 0
        self._scroll_y: int = 0

        # ---- Internal storage ----
        self.oam: bytearray = bytearray(256)     # Object Attribute Memory
        self.palette: bytearray = bytearray(32)  # Palette RAM (32 bytes)
        self.framebuffer: list[int] = [0] * (256 * 240)  # RGB frame buffer
        self.scanline: int = 0
        self.cycle: int = 0
        self.frame_complete: bool = False
        self.nmi_callback: Callable[[], None] | None = None

        # ---- Scanline-level caches (populated at cycle 0 of each visible scanline) ----
        self._bg_scanline: list[int] = [0] * 256  # pre-rendered background pixels
        self._sprite_cache: list[tuple[int, int, int, int, int, int, bool]] = []
        # Each entry: (spr_x, spr_y, tile_idx, attr, palette_group, priority, sprite_zero)
        self._cached_scanline: int = -1  # which scanline the caches were built for

    def reset(self) -> None:
        """Reset all PPU registers and internal state."""
        self.ctrl = 0
        self.mask = 0
        self.status = 0
        self.oam_addr = 0
        self._write_latch = False
        self._scroll_x = 0
        self._scroll_y = 0
        self.vram_addr = 0
        self.read_buffer = 0
        self.scanline = 0
        self.cycle = 0
        self.frame_complete = False
        self.oam = bytearray(256)
        self.palette = bytearray(32)
        self._bg_scanline = [0] * 256
        self._sprite_cache = []
        self._cached_scanline = -1

    # ------------------------------------------------------------------
    #  CPU-side register read / write ($2000-$2007)
    # ------------------------------------------------------------------

    def cpu_read(self, address: int) -> int:
        """CPU reads a PPU register (address is already in 0x2000-0x2007 range).

        register             | R/W  | behaviour
        ---------------------+------+-------------------------------------
        0x2002  PPUSTATUS    |  R   | returns status; clears VBlank + latch
        0x2004  OAMDATA      |  R   | returns OAM[oam_addr]
        0x2007  PPUDATA      |  R   | returns read_buffer, then pre-reads
        """
        reg = 0x2000 + (address & 0x07)

        if reg == 0x2002:  # PPUSTATUS
            result = self.status
            self.status &= 0x7F   # clear VBlank flag (bit 7)
            self._write_latch = False
            # low 5 bits reflect bus noise (previous value on data bus)
            return result | (result & 0x1F)

        if reg == 0x2004:  # OAMDATA
            return self.oam[self.oam_addr]

        if reg == 0x2007:  # PPUDATA
            addr = self.vram_addr & 0x3FFF
            value = self.read_buffer

            if addr >= 0x3F00:
                # Palette region: read from internal palette RAM directly.
                value = self._read_palette(addr)
                self.read_buffer = self._read_palette(
                    (addr + self._addr_increment()) & 0x3FFF
                )
            else:
                self.read_buffer = self.ppu_bus.read(addr)

            self.vram_addr = (self.vram_addr + self._addr_increment()) & 0xFFFF
            return value

        return 0

    def cpu_write(self, address: int, value: int) -> None:
        """CPU writes to a PPU register (address is already in 0x2000-0x2007).

        Any write that may affect the pre-computed scanline caches
        (mask, ctrl, scroll, OAM, palette) invalidates them.
        """
        reg = 0x2000 + (address & 0x07)
        value &= 0xFF

        if reg == 0x2000:  # PPUCTRL
            self.ctrl = value
            self._cached_scanline = -1

        elif reg == 0x2001:  # PPUMASK
            self.mask = value
            self._cached_scanline = -1

        elif reg == 0x2003:  # OAMADDR
            self.oam_addr = value

        elif reg == 0x2004:  # OAMDATA
            self.oam[self.oam_addr] = value
            self.oam_addr = (self.oam_addr + 1) & 0xFF
            self._cached_scanline = -1

        elif reg == 0x2005:  # PPUSCROLL
            if not self._write_latch:
                self._scroll_x = value
            else:
                self._scroll_y = value
            self._write_latch = not self._write_latch
            self._cached_scanline = -1

        elif reg == 0x2006:  # PPUADDR
            if not self._write_latch:
                # high byte (bits 6-7 are ignored, only 14-bit address space)
                self.vram_addr = (self.vram_addr & 0x00FF) | ((value & 0x3F) << 8)
            else:
                self.vram_addr = (self.vram_addr & 0xFF00) | value
            self._write_latch = not self._write_latch

        elif reg == 0x2007:  # PPUDATA
            addr = self.vram_addr & 0x3FFF
            if addr >= 0x3F00:
                self._write_palette(addr, value)
                self._cached_scanline = -1
            else:
                self.ppu_bus.write(addr, value)
            self.vram_addr = (self.vram_addr + self._addr_increment()) & 0xFFFF

    def oam_write(self, index: int, value: int) -> None:
        """Write a single byte to OAM (used during OAM DMA)."""
        self.oam[index & 0xFF] = value & 0xFF
        self._cached_scanline = -1  # invalidate scanline caches

    # ------------------------------------------------------------------
    #  Helper: VRAM address increment
    # ------------------------------------------------------------------

    def _addr_increment(self) -> int:
        """VRAM address increment: 1 (horizontal) or 32 (vertical)."""
        return 32 if (self.ctrl & 0x04) else 1

    # ------------------------------------------------------------------
    #  Helper: Palette read / write (with mirroring)
    # ------------------------------------------------------------------

    def _read_palette(self, address: int) -> int:
        """Read a palette entry, handling $3F10/$3F14/$3F18/$3F1C mirrors."""
        addr = address & 0x1F
        if addr in (0x10, 0x14, 0x18, 0x1C):
            addr -= 0x10  # mirror to 0x00 / 0x04 / 0x08 / 0x0C
        return self.palette[addr]

    def _write_palette(self, address: int, value: int) -> None:
        """Write a palette entry, handling mirroring."""
        addr = address & 0x1F
        if addr in (0x10, 0x14, 0x18, 0x1C):
            addr -= 0x10
        self.palette[addr] = value & 0x3F

    # ------------------------------------------------------------------
    #  Main tick method — advances one PPU cycle
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Advance one PPU cycle (3 PPU cycles per 1 CPU cycle).

        Visible scanlines (0-239): all 256 pixels are rendered at cycle 0
        by ``_build_scanline_caches`` — no per-pixel work during cycles 1-340.
        Scanline 241:               set VBlank + optionally trigger NMI.
        Scanline 261:               pre-render — clear flags, mark frame complete.
        After scanline 261:         wrap back to scanline 0.
        """
        # Build per-scanline caches AND render all 256 pixels at cycle 0
        if self.scanline < 240 and self.cycle == 0:
            self._render_scanline(self.scanline)

        self.cycle += 1
        if self.cycle > 340:
            self.cycle = 0
            self.scanline += 1

            if self.scanline == 241:
                self._set_vblank()
            elif self.scanline == 261:
                # Pre-render line: clear VBlank, sprite-0 hit, sprite overflow
                self.status &= 0x1F
                self.frame_complete = True
            elif self.scanline > 261:
                self.scanline = 0

    def _fast_forward_vblank(self) -> None:
        """Skip directly to the end of VBlank.

        Called from the emulator loop when the PPU has entered VBlank
        (scanline >= 241) and we want to skip the remaining ~6 820 PPU
        cycles that do nothing but increment counters.

        Sets ``scanline=261``, ``cycle=0``, clears status flags, and marks
        the frame complete — exactly as if we had ticked through every
        remaining VBlank cycle.
        """
        self.cycle = 0
        self.scanline = 261
        self.status &= 0x1F
        self.frame_complete = True

    def tick_batch(self, n: int) -> None:
        """Advance PPU by *n* cycles — batch version of :meth:`tick`.

        Avoids the per-cycle Python function-call overhead of the old
        ``for _ in range(n): ppu.tick()`` pattern.  During VBlank
        (scanlines 241-260) the cycles are advanced in bulk without
        per-cycle work, but the frame is NOT marked complete early —
        the CPU must still run during VBlank to update PPU registers.

        This is the preferred entry point for the emulator hot loop.
        """
        # Wrap from post-render into the next frame
        if self.scanline >= 261:
            self.scanline = 0

        while n > 0 and not self.frame_complete:
            # ── VBlank / post-render (scanlines 241-260) ────────────
            if self.scanline >= 241:
                # Advance in bulk through remaining VBlank scanlines.
                # Each VBlank scanline = 341 cycles of pure overhead.
                remaining_in_vblank = (261 - self.scanline) * 341 - self.cycle
                if n >= remaining_in_vblank:
                    # Complete the frame
                    n -= remaining_in_vblank
                    self.cycle = 0
                    self.scanline = 261
                    self.status &= 0x1F
                    self.frame_complete = True
                    return
                # Partial advance within VBlank
                self.cycle += n
                extra_scanlines = self.cycle // 341
                self.scanline += extra_scanlines
                self.cycle %= 341
                n = 0
                if self.scanline >= 261:
                    self.cycle = 0
                    self.scanline = 261
                    self.status &= 0x1F
                    self.frame_complete = True
                    return
                continue

            # ── Visible scanlines (0-239) ──────────────────────────
            if self.scanline < 240 and self.cycle == 0:
                self._render_scanline(self.scanline)

            remaining = 341 - self.cycle
            advance = min(n, remaining)
            self.cycle += advance
            n -= advance

            if self.cycle > 340:
                self.cycle = 0
                self.scanline += 1
                if self.scanline == 241:
                    self._set_vblank()
                elif self.scanline == 261:
                    self.status &= 0x1F
                    self.frame_complete = True
                    return

    def _set_vblank(self) -> None:
        """Set the VBlank flag and trigger NMI if enabled."""
        self.status |= 0x80                # set VBlank flag (bit 7)
        if (self.ctrl & 0x80) and self.nmi_callback is not None:
            self.nmi_callback()

    # ------------------------------------------------------------------
    #  Optimised scanline renderer (called once per visible scanline)
    # ------------------------------------------------------------------

    def _render_scanline(self, y: int) -> None:
        """Render all 256 pixels of scanline *y* into ``self.framebuffer``.

        This replaces the old two-phase approach (``_build_scanline_caches``
        at cycle 0 + 256 ``_render_pixel`` calls across cycles 0-255) with a
        single optimised pass:

        - Background: tile-by-tile iteration (~10× fewer PPUBus reads)
        - Sprites:     pre-compute pixel overlay for the scanline once
        - Composite:   single tight loop over 256 pixels → framebuffer

        Performance: ~15-20× faster than the old per-pixel approach.
        """
        # ── Local bindings (avoid repeated attribute lookups) ─────
        ppu_bus_read = self.ppu_bus.read
        ctrl = self.ctrl
        mask = self.mask
        sx = self._scroll_x
        sy = self._scroll_y
        read_palette = self._read_palette
        get_color_fn = get_color
        fb_row_start = y * 256
        fb = self.framebuffer

        scrolled_y = (y + sy) % 480
        nt_y_mask = 0x0800 if scrolled_y >= 240 else 0
        fine_y = scrolled_y & 7
        tile_y = (scrolled_y % 240) // 8

        # ═══════════════════════════════════════════════════════════
        #  Phase 1: Build background pixels (tile-by-tile)
        # ═══════════════════════════════════════════════════════════
        bg = self._bg_scanline  # reuse pre-allocated buffer

        if mask & 0x08:  # background enabled
            bg_color0 = get_color_fn(read_palette(0))
            pattern_base = 0x1000 if (ctrl & 0x10) else 0x0000

            # Iterate over 33 tile positions (0-32) to handle the case
            # where scrolling causes a single screen row to span 33 tiles
            # (when sx % 8 ≠ 0 and the row crosses a nametable boundary).
            for tile_col in range(33):
                x_base = tile_col * 8 - (sx & 7)
                if x_base >= 256:
                    break

                # Compute the *first* pixel's scrolled position for this tile
                first_x = max(0, x_base)
                scrolled_x0 = (first_x + sx) % 512
                nt_base = 0x2000 | (0x0400 if scrolled_x0 >= 256 else 0) | nt_y_mask

                tile_idx_x = (scrolled_x0 & 0xFF) // 8

                # ── Read tile index (once per tile, saves 8× reads) ─
                tile_index = ppu_bus_read(nt_base + tile_y * 32 + tile_idx_x)

                # ── Read attribute (once per 2×2-tile block) ─
                attr_addr = (
                    0x23C0 | (nt_base & 0x0C00)
                    | ((tile_y // 4) * 8) | (tile_idx_x // 4)
                )
                attr_byte = ppu_bus_read(attr_addr)
                shift = ((tile_y & 2) << 1) | (tile_idx_x & 2)
                palette_group = (attr_byte >> shift) & 0x03

                # ── Read pattern row (2 bytes for all 8 pixels of this tile row) ─
                pattern_addr = pattern_base + tile_index * 16 + fine_y
                low_byte = ppu_bus_read(pattern_addr)
                high_byte = ppu_bus_read(pattern_addr + 8)

                # Pre-compute palette addresses for color indices 1,2,3
                pal_addr_1 = 0x3F00 + palette_group * 4 + 1
                pal_addr_2 = 0x3F00 + palette_group * 4 + 2
                pal_addr_3 = 0x3F00 + palette_group * 4 + 3
                c1 = get_color_fn(read_palette(pal_addr_1))
                c2 = get_color_fn(read_palette(pal_addr_2))
                c3 = get_color_fn(read_palette(pal_addr_3))

                # ── Decode all 8 pixels ───────────────────────────
                for px in range(8):
                    x = x_base + px
                    if x < 0 or x >= 256:
                        continue

                    # Need to check if scrolled position crosses nametable
                    scrolled_x = (x + sx) % 512
                    cur_nt_bit = 0x0400 if scrolled_x >= 256 else 0

                    if cur_nt_bit != (nt_base & 0x0400):
                        # Crossed nametable boundary mid-tile — rare, handle inline
                        cur_nt = 0x2000 | cur_nt_bit | nt_y_mask
                        cur_tx = (scrolled_x & 0xFF) // 8
                        cur_ti = ppu_bus_read(cur_nt + tile_y * 32 + cur_tx)
                        cur_attr_a = (0x23C0 | (cur_nt & 0x0C00)
                                      | ((tile_y // 4) * 8) | (cur_tx // 4))
                        cur_attr_b = ppu_bus_read(cur_attr_a)
                        cur_shift = ((tile_y & 2) << 1) | (cur_tx & 2)
                        cur_pg = (cur_attr_b >> cur_shift) & 0x03
                        cur_pat = pattern_base + cur_ti * 16 + fine_y
                        cur_lo = ppu_bus_read(cur_pat)
                        cur_hi = ppu_bus_read(cur_pat + 8)
                        fine_x = scrolled_x & 7
                        bit_pos = 7 - fine_x
                        ci = ((cur_hi >> bit_pos) & 1) << 1 | ((cur_lo >> bit_pos) & 1)
                        if ci == 0:
                            bg[x] = bg_color0
                        else:
                            bg[x] = get_color_fn(read_palette(0x3F00 + cur_pg * 4 + ci))
                    else:
                        fine_x = scrolled_x & 7
                        bit_pos = 7 - fine_x
                        low_bit = (low_byte >> bit_pos) & 1
                        high_bit = (high_byte >> bit_pos) & 1
                        color_index = (high_bit << 1) | low_bit

                        if color_index == 0:
                            bg[x] = bg_color0
                        elif color_index == 1:
                            bg[x] = c1
                        elif color_index == 2:
                            bg[x] = c2
                        else:
                            bg[x] = c3
        else:
            # Background disabled → all transparent
            for x in range(256):
                bg[x] = 0

        # ═══════════════════════════════════════════════════════════
        #  Phase 2: Build sprite pixel overlay for this scanline
        # ═══════════════════════════════════════════════════════════
        # spr_color[x]  = sprite pixel colour at x (0 = transparent)
        # spr_prio[x]   = sprite priority at x (0 = front, 1 = behind bg)
        # spr_zero[x]   = True if this pixel belongs to sprite 0
        spr_color = [0] * 256
        spr_prio = [0] * 256
        spr_zero = [False] * 256

        if mask & 0x10:  # sprites enabled
            sprite_height = 16 if (ctrl & 0x20) else 8
            pattern_base_spr = 0x1000 if (ctrl & 0x08) else 0x0000
            oam = self.oam
            sprites_on_line = 0

            for i in range(64):
                spr_y = (oam[i * 4] + 1) & 0xFF
                if y < spr_y or y >= spr_y + sprite_height:
                    continue

                tile_index = oam[i * 4 + 1]
                attr = oam[i * 4 + 2]
                spr_x = oam[i * 4 + 3]
                palette_group = attr & 0x03
                priority = (attr >> 5) & 1
                is_sprite_zero = (i == 0)

                flip_v = (attr >> 7) & 1
                flip_h = (attr >> 6) & 1

                sprite_y_offset = y - spr_y
                tile_row = sprite_y_offset if not flip_v else sprite_height - 1 - sprite_y_offset

                # Read pattern data for this sprite row
                if sprite_height == 8:
                    pat_addr = pattern_base_spr + tile_index * 16 + tile_row
                else:
                    bank = tile_index & 1
                    base_tile = tile_index & 0xFE
                    if tile_row >= 8:
                        pat_addr = 0x1000 * bank + (base_tile + 1) * 16 + (tile_row - 8)
                    else:
                        pat_addr = 0x1000 * bank + base_tile * 16 + tile_row

                lo = ppu_bus_read(pat_addr)
                hi = ppu_bus_read(pat_addr + 8)

                # Pre-compute palette colors for indices 1,2,3
                pal_addr_1 = 0x3F10 + palette_group * 4 + 1
                pal_addr_2 = 0x3F10 + palette_group * 4 + 2
                pal_addr_3 = 0x3F10 + palette_group * 4 + 3
                sp_c1 = get_color_fn(read_palette(pal_addr_1))
                sp_c2 = get_color_fn(read_palette(pal_addr_2))
                sp_c3 = get_color_fn(read_palette(pal_addr_3))

                # Render 8 pixels of this sprite
                for px in range(8):
                    x = spr_x + px
                    if x < 0 or x >= 256:
                        continue
                    if spr_color[x] != 0:
                        continue  # earlier (lower-index) sprite already occupies this pixel

                    pixel_col = px if not flip_h else 7 - px
                    bit_pos = 7 - pixel_col
                    ci = ((hi >> bit_pos) & 1) << 1 | ((lo >> bit_pos) & 1)

                    if ci == 0:
                        continue

                    if ci == 1:
                        spr_color[x] = sp_c1
                    elif ci == 2:
                        spr_color[x] = sp_c2
                    else:
                        spr_color[x] = sp_c3
                    spr_prio[x] = priority
                    spr_zero[x] = is_sprite_zero

                sprites_on_line += 1
                if sprites_on_line >= 8:
                    break

        # ═══════════════════════════════════════════════════════════
        #  Phase 3: Composite background + sprites → framebuffer
        # ═══════════════════════════════════════════════════════════
        for x in range(256):
            sc = spr_color[x]
            bc = bg[x]

            if sc and (spr_prio[x] == 0 or bc == 0):
                fb[fb_row_start + x] = sc
            else:
                fb[fb_row_start + x] = bc

            # Sprite-0 collision detection
            if spr_zero[x] and bc and sc and x < 255:
                self.status |= 0x40

        # Update cached scanline index for lazy-access compatibility
        self._cached_scanline = y
        # Keep sprite cache empty — old _get_sprite_pixel path is deprecated

    def _build_scanline_caches(self, y: int | None = None) -> None:
        """Backward-compatibility shim — delegates to ``_render_scanline``."""
        if y is None:
            y = self.scanline
        self._render_scanline(y)

    # ------------------------------------------------------------------
    #  Pixel rendering: composition
    # ------------------------------------------------------------------

    def _render_pixel(self, x: int, y: int) -> None:
        """Render the pixel at screen coordinate (x, y).

        Computes background and sprite colour independently (does not
        depend on or trigger the batch ``_render_scanline`` path), so it
        is safe to call from tests or for single-pixel queries.

        Composition rules:
        1. If sprite pixel is non-transparent AND
           (sprite priority == 0 (front) OR background is transparent),
           → sprite colour.
        2. Otherwise → background colour.
        3. If sprite-0 hit conditions met → set flag.
        """
        bg_color = self._get_background_pixel(x, y)
        spr_color, spr_priority, sprite_zero = self._get_sprite_pixel(x, y)

        # Priority compositing
        final = spr_color if spr_color and (spr_priority == 0 or bg_color == 0) else bg_color

        # Sprite-0 collision detection
        if sprite_zero and bg_color and spr_color and x < 255:
            self.status |= 0x40  # set sprite-0 hit flag (bit 6)

        self.framebuffer[y * 256 + x] = final

    # ------------------------------------------------------------------
    #  Background rendering
    # ------------------------------------------------------------------

    def _get_background_pixel(self, x: int, y: int) -> int:
        """Return the RGB colour of the background layer at (x, y).

        Returns 0 if background rendering is disabled (mask bit 3).

        Steps:
        1. Apply scroll offset (wrap at 512×480 nametable space).
        2. Determine which nametable the pixel falls in.
        3. Read the tile index from the nametable.
        4. Read the palette group from the attribute table.
        5. Read the tile bitmap (low and high bit-planes) from CHR-ROM.
        6. Combine the two bit-planes into a 2-bit colour index.
        7. Look up the final colour in palette RAM.
        """
        if not (self.mask & 0x08):  # background rendering disabled
            return 0

        # 1. Apply scroll
        scrolled_x = (x + self._scroll_x) % 512
        scrolled_y = (y + self._scroll_y) % 480

        # 2. Nametable base
        nt_base = 0x2000
        if scrolled_x >= 256:
            nt_base ^= 0x0400
        if scrolled_y >= 240:
            nt_base ^= 0x0800

        tile_x = (scrolled_x % 256) // 8
        tile_y = (scrolled_y % 240) // 8
        fine_x = scrolled_x % 8
        fine_y = scrolled_y % 8

        # 3. Read tile index from nametable
        tile_addr = nt_base + tile_y * 32 + tile_x
        tile_index = self.ppu_bus.read(tile_addr)

        # 4. Read attribute table
        attr_addr = (
            0x23C0
            | (nt_base & 0x0C00)
            | ((tile_y // 4) * 8)
            | (tile_x // 4)
        )
        attr_byte = self.ppu_bus.read(attr_addr)
        # Each 2-bit field covers a 2×2 tile block.
        # Bit-pair selection order within the 4×4 tile group:
        #   Top-left    : ((tile_y%4 // 2) << 1) | (tile_x%4 // 2)
        #   → shift = ((tile_y & 2) << 1) | (tile_x & 2)
        shift = ((tile_y & 2) << 1) | (tile_x & 2)
        palette_group = (attr_byte >> shift) & 0x03

        # 5. Read tile bitmap from CHR-ROM
        pattern_base = 0x1000 if (self.ctrl & 0x10) else 0x0000
        # Each tile occupies 16 bytes in pattern memory:
        #   bytes 0-7    → low bit-plane  (8 rows)
        #   bytes 8-15   → high bit-plane (8 rows)
        pattern_addr = pattern_base + tile_index * 16 + fine_y
        low_byte = self.ppu_bus.read(pattern_addr)
        high_byte = self.ppu_bus.read(pattern_addr + 8)

        # 6. Extract the 2-bit colour index for this pixel
        bit_pos = 7 - fine_x
        low_bit = (low_byte >> bit_pos) & 1
        high_bit = (high_byte >> bit_pos) & 1
        color_index = (high_bit << 1) | low_bit

        if color_index == 0:
            # Universal background colour (palette index 0)
            return get_color(self._read_palette(0))

        # 7. Palette lookup: 0x3F00 + palette_group*4 + color_index
        palette_addr = 0x3F00 + palette_group * 4 + color_index
        return get_color(self._read_palette(palette_addr))

    # ------------------------------------------------------------------
    #  Sprite rendering
    # ------------------------------------------------------------------

    def _get_sprite_pixel(self, x: int, y: int) -> tuple[int, int, bool]:
        """Return (colour, priority, is_sprite_zero) for the sprite layer at (x, y).

        Scans OAM directly — does not depend on the per-scanline cache
        (which is only used by ``_render_scanline`` for the batch path).

        Sprites are evaluated in OAM index order (0 first, i.e. lowest
        index = highest priority).  The first non-transparent sprite pixel
        that covers (x, y) wins.

        If no visible sprite pixel covers this coordinate the return value
        is (0, 0, False).
        """
        if not (self.mask & 0x10):  # sprites disabled
            return (0, 0, False)

        ctrl = self.ctrl
        sprite_height = 16 if (ctrl & 0x20) else 8
        pattern_base_spr = 0x1000 if (ctrl & 0x08) else 0x0000
        ppu_bus_read = self.ppu_bus.read
        read_palette = self._read_palette
        get_color_fn = get_color
        oam = self.oam
        sprites_on_line = 0

        for i in range(64):
            spr_y = (oam[i * 4] + 1) & 0xFF
            if y < spr_y or y >= spr_y + sprite_height:
                continue

            tile_index = oam[i * 4 + 1]
            attr = oam[i * 4 + 2]
            spr_x = oam[i * 4 + 3]

            if x < spr_x or x >= spr_x + 8:
                continue

            sprites_on_line += 1
            if sprites_on_line > 8:
                break  # only first 8 sprites per scanline are evaluated

            palette_group = attr & 0x03
            priority = (attr >> 5) & 1
            is_sprite_zero = (i == 0)

            flip_v = (attr >> 7) & 1
            flip_h = (attr >> 6) & 1

            sprite_y_offset = y - spr_y
            tile_row = sprite_y_offset if not flip_v else sprite_height - 1 - sprite_y_offset
            pixel_col = x - spr_x if not flip_h else 7 - (x - spr_x)

            if sprite_height == 8:
                pattern_addr = pattern_base_spr + tile_index * 16 + tile_row
            else:
                bank = tile_index & 1
                base_tile = tile_index & 0xFE
                if tile_row >= 8:
                    pattern_addr = 0x1000 * bank + (base_tile + 1) * 16 + (tile_row - 8)
                else:
                    pattern_addr = 0x1000 * bank + base_tile * 16 + tile_row

            low_byte = ppu_bus_read(pattern_addr)
            high_byte = ppu_bus_read(pattern_addr + 8)

            bit_pos = 7 - pixel_col
            low_bit = (low_byte >> bit_pos) & 1
            high_bit = (high_byte >> bit_pos) & 1
            color_index = (high_bit << 1) | low_bit

            if color_index == 0:
                continue  # transparent pixel

            palette_addr = 0x3F10 + palette_group * 4 + color_index
            color = get_color_fn(read_palette(palette_addr))
            return (color, priority, is_sprite_zero)

        return (0, 0, False)

