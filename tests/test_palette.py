"""Unit tests for src/palette.py."""

from __future__ import annotations

from src.palette import PALETTE, get_color


class TestPalette:
    """Tests covering the FC system palette table and lookup function."""

    def test_palette_size(self) -> None:
        """The PALETTE list must contain exactly 64 entries."""
        assert len(PALETTE) == 64

    def test_get_color(self) -> None:
        """get_color(0) returns the first palette entry (0x666666)."""
        assert get_color(0) == 0x666666

    def test_get_color_wrap(self) -> None:
        """get_color(64) wraps around to index 0 via the 0x3F bitmask."""
        assert get_color(64) == get_color(0)
        assert get_color(127) == get_color(63)
        assert get_color(128) == get_color(0)

    def test_palette_all_valid_rgb(self) -> None:
        """Every palette entry is a valid 24-bit RGB value (<= 0xFFFFFF)."""
        for i, color in enumerate(PALETTE):
            assert isinstance(color, int), f"PALETTE[{i}] is not an int"
            assert 0 <= color <= 0xFFFFFF, (
                f"PALETTE[{i}] = 0x{color:06X} is out of 24-bit range"
            )

    def test_get_color_specific_indices(self) -> None:
        """Spot-check a few known palette entries via get_color."""
        assert get_color(0x0F) == 0x000000  # black placeholder
        assert get_color(0x10) == 0xADADAD  # light gray
        assert get_color(0x20) == 0xFFFEFF  # white
        assert get_color(0x30) == 0xFFFEFF  # white
        assert get_color(0x3F) == 0x000000  # black placeholder

    def test_palette_immutable_snapshot(self) -> None:
        """Verify canonical NES palette values.

        Specific, well-known palette entries should match the widely-used
        NES palette values.
        """
        # Row 0 (indices 0x00–0x0F)
        assert PALETTE[0x00] == 0x666666
        assert PALETTE[0x01] == 0x002A88
        assert PALETTE[0x02] == 0x1412A7
        assert PALETTE[0x04] == 0x5C007E
        assert PALETTE[0x08] == 0x333400

        # Row 1 (indices 0x10–0x1F)
        assert PALETTE[0x10] == 0xADADAD
        assert PALETTE[0x12] == 0x4240FF

        # Row 2 (indices 0x20–0x2F)
        assert PALETTE[0x20] == 0xFFFEFF
        assert PALETTE[0x2D] == 0x4F4F4F

        # Row 3 (indices 0x30–0x3F)
        assert PALETTE[0x30] == 0xFFFEFF
        assert PALETTE[0x3D] == 0xB8B8B8
