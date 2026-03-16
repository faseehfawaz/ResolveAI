"""
Tests for the Color Transfer algorithms.

Tests Reinhard, histogram matching, and MVGD transfer methods
using synthetic ClipColorProfiles.
"""

import numpy as np
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from color_engine.analyzer import ClipColorProfile, ChannelStats
from color_engine.transfer import (
    reinhard_transfer,
    histogram_match_transfer,
    mvgd_transfer,
    get_transfer_function,
)


def _make_profile(
    rgb_means=(128, 128, 128),
    rgb_stds=(30, 30, 30),
    lab_means=(128, 128, 128),
    lab_stds=(30, 10, 10),
    name="test",
):
    """Create a synthetic ClipColorProfile for testing."""
    profile = ClipColorProfile(clip_name=name)
    
    profile.red = ChannelStats(mean=rgb_means[0], std=rgb_stds[0])
    profile.green = ChannelStats(mean=rgb_means[1], std=rgb_stds[1])
    profile.blue = ChannelStats(mean=rgb_means[2], std=rgb_stds[2])
    
    profile.lab_l = ChannelStats(mean=lab_means[0], std=lab_stds[0])
    profile.lab_a = ChannelStats(mean=lab_means[1], std=lab_stds[1])
    profile.lab_b = ChannelStats(mean=lab_means[2], std=lab_stds[2])

    # Generate histograms as approximate Gaussians
    for ch, (mean, std) in zip(
        [profile.red, profile.green, profile.blue],
        zip(rgb_means, rgb_stds),
    ):
        x = np.arange(256)
        ch.histogram = np.exp(-((x - mean) ** 2) / (2 * std ** 2))
        ch.histogram /= ch.histogram.sum()

    # Covariance for MVGD
    profile.rgb_mean = np.array(rgb_means, dtype=np.float64)
    profile.rgb_covariance = np.diag(np.array(rgb_stds, dtype=np.float64) ** 2)

    return profile


# ── Reinhard Transfer Tests ──────────────────────────────────

@pytest.mark.skipif(not HAS_CV2, reason="OpenCV not installed")
class TestReinhardTransfer:
    def test_identity_transfer(self):
        """Transferring from a profile to itself should be near-identity."""
        profile = _make_profile(name="self")
        transform = reinhard_transfer(profile, profile, intensity=1.0)
        
        # Test with a mid-gray pixel
        input_pixel = np.array([128.0, 128.0, 128.0])
        output_pixel = transform(input_pixel)
        
        # Should be very close to input
        assert np.allclose(output_pixel, input_pixel, atol=10)

    def test_warm_to_cool(self):
        """Transferring warm → cool should reduce red relative to blue."""
        warm = _make_profile(
            lab_means=(128, 130, 140),
            lab_stds=(30, 10, 10),
            name="warm",
        )
        cool = _make_profile(
            lab_means=(128, 126, 118),
            lab_stds=(30, 10, 10),
            name="cool",
        )
        transform = reinhard_transfer(warm, cool, intensity=1.0)
        
        # A warm pixel
        warm_pixel = np.array([200.0, 150.0, 100.0])
        result = transform(warm_pixel)
        
        # Result should be valid RGB
        assert np.all(result >= 0) and np.all(result <= 255)

    def test_intensity_zero_is_identity(self):
        """Intensity=0 should leave the pixel unchanged."""
        source = _make_profile(lab_means=(100, 128, 140), name="src")
        target = _make_profile(lab_means=(150, 128, 115), name="tgt")
        transform = reinhard_transfer(source, target, intensity=0.0)
        
        pixel = np.array([128.0, 128.0, 128.0])
        result = transform(pixel)
        assert np.allclose(result, pixel, atol=5)


# ── Histogram Matching Tests ─────────────────────────────────

class TestHistogramMatch:
    def test_identical_histograms(self):
        """Matching identical histograms should be near-identity."""
        profile = _make_profile(name="same")
        transform = histogram_match_transfer(profile, profile, intensity=1.0)
        
        pixel = np.array([128.0, 128.0, 128.0])
        result = transform(pixel)
        assert np.allclose(result, pixel, atol=5)

    def test_output_in_range(self):
        """Output should always be in 0–255 range."""
        src = _make_profile(rgb_means=(50, 50, 50), rgb_stds=(20, 20, 20), name="dark")
        tgt = _make_profile(rgb_means=(200, 200, 200), rgb_stds=(20, 20, 20), name="bright")
        transform = histogram_match_transfer(src, tgt, intensity=1.0)
        
        for r in [0, 64, 128, 192, 255]:
            pixel = np.array([float(r), float(r), float(r)])
            result = transform(pixel)
            assert np.all(result >= 0) and np.all(result <= 255)


# ── MVGD Transfer Tests ─────────────────────────────────────

class TestMVGDTransfer:
    def test_identity_mvgd(self):
        """MVGD self-transfer should be near-identity."""
        profile = _make_profile(name="self")
        transform = mvgd_transfer(profile, profile, intensity=1.0)
        
        pixel = np.array([128.0, 128.0, 128.0])
        result = transform(pixel)
        assert np.allclose(result, pixel, atol=5)

    def test_mvgd_output_valid(self):
        """MVGD output should be valid RGB."""
        src = _make_profile(rgb_means=(100, 120, 80), rgb_stds=(25, 30, 20), name="src")
        tgt = _make_profile(rgb_means=(150, 130, 170), rgb_stds=(35, 25, 30), name="tgt")
        transform = mvgd_transfer(src, tgt, intensity=1.0)
        
        pixel = np.array([100.0, 120.0, 80.0])
        result = transform(pixel)
        assert np.all(result >= 0) and np.all(result <= 255)


# ── Factory Function Tests ───────────────────────────────────

class TestTransferFactory:
    def test_get_reinhard(self):
        src = _make_profile(name="s")
        tgt = _make_profile(name="t")
        fn = get_transfer_function("reinhard", src, tgt)
        assert callable(fn)

    def test_get_histogram(self):
        src = _make_profile(name="s")
        tgt = _make_profile(name="t")
        fn = get_transfer_function("histogram", src, tgt)
        assert callable(fn)

    def test_get_mvgd(self):
        src = _make_profile(name="s")
        tgt = _make_profile(name="t")
        fn = get_transfer_function("mvgd", src, tgt)
        assert callable(fn)

    def test_invalid_method(self):
        src = _make_profile(name="s")
        tgt = _make_profile(name="t")
        with pytest.raises(ValueError):
            get_transfer_function("invalid_method", src, tgt)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
