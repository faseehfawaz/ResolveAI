"""
Tests for the 3D LUT Generator.

Tests .cube file generation, identity LUT validation, and combined
normalization+creative LUT generation.
"""

import os
import sys
import numpy as np
import pytest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from color_engine.lut_generator import (
    generate_3d_lut,
    generate_identity_lut,
    generate_lut_with_normalization,
)


class TestLUTGeneration:
    def test_identity_lut_file_created(self):
        """Identity LUT should create a valid .cube file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_identity.cube")
            result = generate_identity_lut(lut_size=5, output_path=path)
            
            assert os.path.isfile(result)
            assert result == path

    def test_identity_lut_content(self):
        """Identity LUT should map every point to itself."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "identity.cube")
            generate_identity_lut(lut_size=5, output_path=path)
            
            with open(path, "r") as f:
                content = f.read()
            
            # Should have TITLE and LUT_3D_SIZE headers
            assert "TITLE" in content
            assert "LUT_3D_SIZE 5" in content
            
            # Parse data lines
            data_lines = [
                line.strip() for line in content.split("\n")
                if line.strip() and not line.startswith("#")
                and not line.startswith("TITLE")
                and not line.startswith("LUT_3D")
                and not line.startswith("DOMAIN")
            ]
            
            # Should have 5^3 = 125 data lines
            assert len(data_lines) == 125
            
            # Each line should have 3 float values
            for line in data_lines:
                values = [float(v) for v in line.split()]
                assert len(values) == 3
                # All values should be in 0–1 range
                assert all(0.0 <= v <= 1.0 for v in values)

    def test_identity_lut_maps_to_self(self):
        """In an identity LUT, the diagonal points should map to themselves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "identity.cube")
            generate_identity_lut(lut_size=5, output_path=path)
            
            with open(path, "r") as f:
                lines = f.readlines()
            
            data_lines = [
                line.strip() for line in lines
                if line.strip() and not line.startswith("#")
                and not line.startswith("TITLE")
                and not line.startswith("LUT_3D")
                and not line.startswith("DOMAIN")
            ]
            
            # Check corners: first entry (0,0,0) → (0,0,0)
            first = [float(v) for v in data_lines[0].split()]
            assert all(abs(v) < 0.02 for v in first)
            
            # Last entry (1,1,1) → (1,1,1)
            last = [float(v) for v in data_lines[-1].split()]
            assert all(abs(v - 1.0) < 0.02 for v in last)

    def test_custom_transform_lut(self):
        """A custom transform should produce a valid LUT file."""
        def invert(rgb):
            return 255.0 - rgb
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "invert.cube")
            result = generate_3d_lut(
                invert, lut_size=5,
                title="Invert Test",
                output_path=path,
            )
            assert os.path.isfile(result)
            
            with open(result, "r") as f:
                content = f.read()
            
            assert "Invert Test" in content

    def test_combined_normalization_lut(self):
        """Combined normalization + creative LUT should generate correctly."""
        norm_cdl = {
            "slope": (1.1, 1.0, 0.9),
            "offset": (0.02, 0.0, -0.02),
            "power": (0.95, 1.0, 1.05),
        }
        
        def creative_fn(rgb):
            # Simple desaturation
            gray = np.mean(rgb)
            return rgb * 0.7 + gray * 0.3
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "combined.cube")
            result = generate_lut_with_normalization(
                normalization_cdl=norm_cdl,
                creative_transform_fn=creative_fn,
                lut_size=5,
                clip_name="test_clip",
                output_path=path,
            )
            assert os.path.isfile(result)

    def test_lut_size_affects_entries(self):
        """Different LUT sizes should produce different numbers of entries."""
        def identity(rgb):
            return rgb
        
        with tempfile.TemporaryDirectory() as tmpdir:
            for size in [3, 5, 9]:
                path = os.path.join(tmpdir, f"size_{size}.cube")
                generate_3d_lut(identity, lut_size=size, output_path=path)
                
                with open(path, "r") as f:
                    lines = f.readlines()
                
                data_lines = [
                    l for l in lines
                    if l.strip() and not l.startswith("#")
                    and not l.startswith("TITLE")
                    and not l.startswith("LUT_3D")
                    and not l.startswith("DOMAIN")
                ]
                
                assert len(data_lines) == size ** 3


class TestLUTEdgeCases:
    def test_transform_that_clips(self):
        """Transform that overshoots 0–255 should be clamped in the LUT."""
        def overexpose(rgb):
            return rgb * 3.0  # Will exceed 255
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "clip.cube")
            generate_3d_lut(overexpose, lut_size=5, output_path=path)
            
            with open(path, "r") as f:
                lines = f.readlines()
            
            data_lines = [
                l.strip() for l in lines
                if l.strip() and not l.startswith("#")
                and not l.startswith("TITLE")
                and not l.startswith("LUT_3D")
                and not l.startswith("DOMAIN")
            ]
            
            # All values should be clamped to 0–1
            for line in data_lines:
                values = [float(v) for v in line.split()]
                assert all(0.0 <= v <= 1.0 for v in values)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
