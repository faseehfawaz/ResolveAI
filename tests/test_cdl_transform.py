"""
Tests for the CDL Transform Calculator.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_engine.analyzer import ClipColorProfile, ChannelStats
from color_engine.cdl_transform import (
    compute_creative_cdl,
    combine_cdl,
    cdl_for_reference_match,
    format_cdl_for_resolve,
    _clamp,
    _lerp,
)


def _make_profile(rgb_means=(128, 128, 128), rgb_stds=(30, 30, 30), name="test"):
    """Create a minimal synthetic ClipColorProfile."""
    p = ClipColorProfile(clip_name=name)
    p.red = ChannelStats(mean=rgb_means[0], std=rgb_stds[0])
    p.green = ChannelStats(mean=rgb_means[1], std=rgb_stds[1])
    p.blue = ChannelStats(mean=rgb_means[2], std=rgb_stds[2])
    p.luminance_mean = sum(rgb_means) / (3 * 255.0)
    p.luminance_std = 0.15
    p.saturation_mean = 0.3
    p.estimated_color_temp = 6500.0
    return p


class TestCreativeCDL:
    def test_identity_self_transfer(self):
        """Transferring to self should produce near-identity CDL."""
        p = _make_profile(name="self")
        cdl = compute_creative_cdl(p, p, intensity=1.0)

        for s in cdl["slope"]:
            assert abs(s - 1.0) < 0.1
        for o in cdl["offset"]:
            assert abs(o) < 0.05

    def test_bright_to_dark_reduces_slope(self):
        """Transferring bright → dark source std should reduce slope."""
        bright = _make_profile(rgb_means=(128, 128, 128), rgb_stds=(60, 60, 60), name="bright")
        dark = _make_profile(rgb_means=(128, 128, 128), rgb_stds=(20, 20, 20), name="dark")
        cdl = compute_creative_cdl(bright, dark, intensity=1.0)
        # Slopes should be < 1 (narrowing the distribution)
        for s in cdl["slope"]:
            assert s < 1.0

    def test_intensity_zero_is_identity(self):
        """Intensity 0 should produce identity CDL."""
        src = _make_profile(rgb_means=(80, 80, 80), name="dark")
        tgt = _make_profile(rgb_means=(200, 200, 200), name="light")
        cdl = compute_creative_cdl(src, tgt, intensity=0.0)

        for s in cdl["slope"]:
            assert abs(s - 1.0) < 0.01
        for o in cdl["offset"]:
            assert abs(o) < 0.01

    def test_all_values_in_range(self):
        """CDL values should be within safe ranges."""
        src = _make_profile(rgb_means=(50, 200, 100), rgb_stds=(10, 50, 30))
        tgt = _make_profile(rgb_means=(200, 80, 150), rgb_stds=(40, 15, 25))
        cdl = compute_creative_cdl(src, tgt, intensity=1.0)

        for s in cdl["slope"]:
            assert 0.5 <= s <= 2.0
        for o in cdl["offset"]:
            assert -0.3 <= o <= 0.3
        for p in cdl["power"]:
            assert 0.3 <= p <= 3.0


class TestCombineCDL:
    def test_identity_combine(self):
        """Combining two identity CDLs should stay identity."""
        identity = {"slope": (1, 1, 1), "offset": (0, 0, 0), "power": (1, 1, 1), "saturation": 1.0}
        combined = combine_cdl(identity, identity)
        for s in combined["slope"]:
            assert abs(s - 1.0) < 0.01
        for o in combined["offset"]:
            assert abs(o) < 0.01

    def test_combine_preserves_direction(self):
        """A warm norm + warm creative should combine warmth."""
        warm_norm = {"slope": (1.05, 1.0, 0.95), "offset": (0.01, 0.0, -0.01),
                     "power": (1.0, 1.0, 1.0), "saturation": 1.0}
        warm_creative = {"slope": (1.03, 1.0, 0.97), "offset": (0.005, 0.0, -0.005),
                         "power": (1.0, 1.0, 1.0), "saturation": 1.0}
        combined = combine_cdl(warm_norm, warm_creative)
        # Red slope should be > 1.0 (combined warmth)
        assert combined["slope"][0] > 1.0
        # Blue slope should be < 1.0
        assert combined["slope"][2] < 1.0


class TestFormatForResolve:
    def test_format_structure(self):
        """Formatted CDL should match Resolve's expected string structure."""
        cdl = {"slope": (1.1, 0.9, 1.0), "offset": (0.01, -0.02, 0.0),
               "power": (1.0, 1.05, 0.95), "saturation": 0.9}
        formatted = format_cdl_for_resolve(cdl, node_index=1)

        assert formatted["NodeIndex"] == "1"
        assert "Slope" in formatted
        assert "Offset" in formatted
        assert "Power" in formatted
        # Values should be space-separated strings
        assert isinstance(formatted["Slope"], str)
        assert isinstance(formatted["Offset"], str)
        slope_parts = formatted["Slope"].split()
        assert len(slope_parts) == 3
        assert abs(float(slope_parts[0]) - 1.1) < 0.001
        assert abs(float(slope_parts[1]) - 0.9) < 0.001
        offset_parts = formatted["Offset"].split()
        assert abs(float(offset_parts[1]) - (-0.02)) < 0.001
        assert "0.9" in formatted["Saturation"]


class TestHelpers:
    def test_clamp(self):
        assert _clamp(5, 0, 10) == 5
        assert _clamp(-5, 0, 10) == 0
        assert _clamp(15, 0, 10) == 10

    def test_lerp(self):
        assert abs(_lerp(0, 10, 0.5) - 5.0) < 0.01
        assert abs(_lerp(0, 10, 0.0) - 0.0) < 0.01
        assert abs(_lerp(0, 10, 1.0) - 10.0) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
