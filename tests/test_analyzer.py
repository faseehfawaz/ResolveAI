"""
Tests for the Color Analyzer module.

Tests color statistics computation, channel analysis, dominant color extraction,
and color temperature estimation using synthetic test images.
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

from color_engine.analyzer import (
    analyze_frames,
    ClipColorProfile,
    _compute_channel_stats,
    _estimate_color_temperature,
    _extract_dominant_colors,
)


def _make_solid_frame(r, g, b, width=100, height=100):
    """Create a solid-color BGR frame (OpenCV format)."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = b  # OpenCV is BGR
    frame[:, :, 1] = g
    frame[:, :, 2] = r
    return frame


def _make_gradient_frame(width=256, height=100):
    """Create a horizontal gradient from black to white (BGR)."""
    gradient = np.zeros((height, width, 3), dtype=np.uint8)
    for x in range(width):
        gradient[:, x, :] = x
    return gradient


# ── Channel Stats Tests ──────────────────────────────────────

class TestChannelStats:
    def test_uniform_channel(self):
        """A solid color should have zero std deviation."""
        values = np.full(10000, 128.0)
        stats = _compute_channel_stats(values)
        assert abs(stats.mean - 128.0) < 0.1
        assert stats.std < 0.1
        assert abs(stats.median - 128.0) < 0.1

    def test_gradient_channel(self):
        """A 0–255 gradient should have mean ~127.5."""
        values = np.arange(256, dtype=np.float64).repeat(100)
        stats = _compute_channel_stats(values)
        assert 125 < stats.mean < 130
        assert abs(stats.min_val) < 1
        assert abs(stats.max_val - 255) < 1
        assert stats.std > 50  # Significant spread

    def test_histogram_normalized(self):
        """Histogram should sum to approximately 1.0."""
        values = np.random.randint(0, 256, size=10000).astype(np.float64)
        stats = _compute_channel_stats(values)
        assert abs(stats.histogram.sum() - 1.0) < 0.01


# ── Color Temperature Tests ──────────────────────────────────

class TestColorTemperature:
    def test_neutral_white(self):
        """Equal R=G=B should give ~6500K."""
        temp = _estimate_color_temperature(128, 128, 128)
        assert 6000 < temp < 7000

    def test_warm_image(self):
        """Red-heavy image should give < 6500K (warm)."""
        temp = _estimate_color_temperature(200, 150, 100)
        assert temp < 6500

    def test_cool_image(self):
        """Blue-heavy image should give > 6500K (cool)."""
        temp = _estimate_color_temperature(100, 130, 200)
        assert temp > 6500


# ── Full Analysis Tests ──────────────────────────────────────

@pytest.mark.skipif(not HAS_CV2, reason="OpenCV not installed")
class TestAnalyzeFrames:
    def test_solid_red_frame(self):
        """A pure red frame should have high red, low green/blue means."""
        frames = [_make_solid_frame(255, 0, 0)]
        profile = analyze_frames(frames, clip_name="test_red")

        assert profile.clip_name == "test_red"
        assert profile.red.mean > 200
        assert profile.green.mean < 50
        assert profile.blue.mean < 50

    def test_solid_gray_frame(self):
        """A neutral gray frame should be balanced and ~6500K."""
        frames = [_make_solid_frame(128, 128, 128)]
        profile = analyze_frames(frames, clip_name="test_gray")

        assert abs(profile.red.mean - profile.green.mean) < 5
        assert abs(profile.green.mean - profile.blue.mean) < 5
        assert 5500 < profile.estimated_color_temp < 7500

    def test_bright_vs_dark(self):
        """A bright frame should have higher luminance than a dark one."""
        bright = [_make_solid_frame(200, 200, 200)]
        dark = [_make_solid_frame(50, 50, 50)]

        bright_profile = analyze_frames(bright, clip_name="bright")
        dark_profile = analyze_frames(dark, clip_name="dark")

        assert bright_profile.luminance_mean > dark_profile.luminance_mean

    def test_saturation_detection(self):
        """A saturated color should have higher saturation than gray."""
        saturated = [_make_solid_frame(255, 0, 0)]
        gray = [_make_solid_frame(128, 128, 128)]

        sat_profile = analyze_frames(saturated, clip_name="saturated")
        gray_profile = analyze_frames(gray, clip_name="gray")

        assert sat_profile.saturation_mean > gray_profile.saturation_mean

    def test_multiple_frames(self):
        """Analyzing multiple frames should work without errors."""
        frames = [
            _make_solid_frame(100, 50, 50),
            _make_solid_frame(150, 100, 100),
            _make_solid_frame(200, 150, 150),
        ]
        profile = analyze_frames(frames, clip_name="multi")
        assert profile.luminance_mean > 0
        assert len(profile.dominant_colors) > 0


# ── Dominant Colors Tests ────────────────────────────────────

class TestDominantColors:
    def test_single_color(self):
        """A solid-color image should have one dominant color."""
        pixels = np.full((10000, 3), [255, 0, 0], dtype=np.float64)
        colors, weights = _extract_dominant_colors(pixels, k=3)
        # The dominant color should be close to (255, 0, 0)
        assert len(colors) > 0
        assert weights[0] > 0.5  # Most pixels in one cluster

    def test_two_colors(self):
        """A 50/50 split should produce two significant clusters."""
        pixels_a = np.full((5000, 3), [255, 0, 0], dtype=np.float64)
        pixels_b = np.full((5000, 3), [0, 0, 255], dtype=np.float64)
        pixels = np.vstack([pixels_a, pixels_b])
        
        colors, weights = _extract_dominant_colors(pixels, k=2)
        assert len(colors) == 2
        assert min(weights) > 0.3  # Both clusters significant


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
