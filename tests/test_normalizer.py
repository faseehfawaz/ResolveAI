"""
Tests for the Exposure & White Balance Normalizer.

Tests exposure correction, white balance correction, and combined
normalization against known synthetic scenarios.
"""

import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_engine.normalizer import (
    compute_exposure_correction,
    compute_white_balance_correction,
    compute_full_normalization,
)


class TestExposureCorrection:
    def test_already_correct_exposure(self):
        """A clip at target luminance should get minimal correction."""
        cdl = compute_exposure_correction(
            luminance_mean=0.45,
            luminance_std=0.15,
            target_luminance=0.45,
        )
        # Offset should be near zero
        assert all(abs(o) < 0.05 for o in cdl["offset"])
        # Slope should be near 1.0
        assert all(abs(s - 1.0) < 0.15 for s in cdl["slope"])

    def test_underexposed_correction(self):
        """An underexposed clip should get positive offset (brighter)."""
        cdl = compute_exposure_correction(
            luminance_mean=0.20,
            luminance_std=0.10,
            target_luminance=0.45,
        )
        # Offset should be positive (lift shadows)
        assert all(o > 0 for o in cdl["offset"])

    def test_overexposed_correction(self):
        """An overexposed clip should get negative offset (darker)."""
        cdl = compute_exposure_correction(
            luminance_mean=0.70,
            luminance_std=0.15,
            target_luminance=0.45,
        )
        # Offset should be negative
        assert all(o < 0 for o in cdl["offset"])

    def test_low_contrast_boost(self):
        """A very low-contrast clip should get a slight slope boost."""
        cdl = compute_exposure_correction(
            luminance_mean=0.45,
            luminance_std=0.02,  # Very flat
            target_luminance=0.45,
        )
        assert all(s >= 1.0 for s in cdl["slope"])

    def test_cdl_values_in_range(self):
        """CDL values should be within reasonable ranges."""
        for lum in [0.05, 0.20, 0.45, 0.70, 0.95]:
            cdl = compute_exposure_correction(lum, 0.15)
            assert all(0.3 <= s <= 3.0 for s in cdl["slope"])
            assert all(-0.5 <= o <= 0.5 for o in cdl["offset"])
            assert all(0.3 <= p <= 3.0 for p in cdl["power"])


class TestWhiteBalanceCorrection:
    def test_neutral_white_balance(self):
        """Neutral RGB means should produce slopes near 1.0."""
        cdl = compute_white_balance_correction(
            r_mean=128, g_mean=128, b_mean=128,
            target_temp=6500,
        )
        assert all(abs(s - 1.0) < 0.1 for s in cdl["slope"])

    def test_warm_cast_correction(self):
        """A warm (red-heavy) image should reduce red slope."""
        cdl = compute_white_balance_correction(
            r_mean=180, g_mean=128, b_mean=90,
            target_temp=6500,
        )
        # Red slope should be < 1 (reduce red)
        assert cdl["slope"][0] < 1.0
        # Blue slope should be > 1 (boost blue)
        assert cdl["slope"][2] > 1.0

    def test_cool_cast_correction(self):
        """A cool (blue-heavy) image should reduce blue slope."""
        cdl = compute_white_balance_correction(
            r_mean=90, g_mean=128, b_mean=180,
            target_temp=6500,
        )
        # Blue slope should be < 1
        assert cdl["slope"][2] < 1.0
        # Red slope should be > 1
        assert cdl["slope"][0] > 1.0

    def test_warm_target_boosts_red(self):
        """A warm target temperature should boost red relative to neutral."""
        neutral = compute_white_balance_correction(
            r_mean=128, g_mean=128, b_mean=128, target_temp=6500
        )
        warm = compute_white_balance_correction(
            r_mean=128, g_mean=128, b_mean=128, target_temp=4500
        )
        # Warm target should have higher red slope than neutral target
        assert warm["slope"][0] >= neutral["slope"][0]

    def test_slopes_in_range(self):
        """Slopes should always be within 0.5–2.0."""
        for r, g, b in [(50, 128, 200), (200, 128, 50), (128, 128, 128)]:
            cdl = compute_white_balance_correction(r, g, b)
            assert all(0.5 <= s <= 2.0 for s in cdl["slope"])


class TestFullNormalization:
    def test_combined_output_structure(self):
        """Combined normalization should have all CDL fields."""
        cdl = compute_full_normalization(
            luminance_mean=0.30,
            luminance_std=0.12,
            r_mean=150, g_mean=128, b_mean=100,
        )
        assert "slope" in cdl
        assert "offset" in cdl
        assert "power" in cdl
        assert "saturation" in cdl
        assert len(cdl["slope"]) == 3
        assert len(cdl["offset"]) == 3
        assert len(cdl["power"]) == 3

    def test_combined_values_clamped(self):
        """Combined values should be within safe ranges."""
        cdl = compute_full_normalization(
            luminance_mean=0.10,
            luminance_std=0.05,
            r_mean=200, g_mean=100, b_mean=50,
        )
        assert all(0.3 <= s <= 3.0 for s in cdl["slope"])
        assert all(-0.5 <= o <= 0.5 for o in cdl["offset"])
        assert all(0.3 <= p <= 3.0 for p in cdl["power"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
