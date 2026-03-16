"""
ResolveAI – AI Color Grading Plugin for DaVinci Resolve Studio
Configuration & Constants
"""

import os

# ── Plugin Info ──────────────────────────────────────────────
PLUGIN_NAME = "ResolveAI"
PLUGIN_VERSION = "0.1.0"
PLUGIN_AUTHOR = "ResolveAI"

# ── Paths ────────────────────────────────────────────────────
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
LOOKS_DIR = os.path.join(PLUGIN_DIR, "looks")
LUTS_DIR = os.path.join(PLUGIN_DIR, "luts")

# Ensure output dirs exist
os.makedirs(LUTS_DIR, exist_ok=True)

# ── LUT Generation ───────────────────────────────────────────
LUT_SIZE = 33  # 33×33×33 cube – industry standard
LUT_TITLE_PREFIX = "ResolveAI"

# ── Color Analysis ───────────────────────────────────────────
FRAMES_PER_CLIP = 5          # Number of representative frames to sample
HISTOGRAM_BINS = 256         # Per-channel histogram resolution
DOMINANT_COLORS_K = 5        # K-means clusters for dominant color extraction

# ── Normalization Targets ────────────────────────────────────
TARGET_LUMINANCE = 0.45      # Target mid-gray (0–1 range, ~18% gray)
TARGET_COLOR_TEMP = 6500     # Target neutral daylight white-balance (Kelvin)

# ── Transfer Algorithm ───────────────────────────────────────
DEFAULT_TRANSFER_METHOD = "reinhard"  # Options: "reinhard", "histogram", "mvgd"

# ── UI Defaults ──────────────────────────────────────────────
DEFAULT_LOOK = "corporate"
DEFAULT_INTENSITY = 100      # 0–100 blend percentage
DEFAULT_MODE = "auto_grade"  # Options: "auto_grade", "match_reference", "single_clip"

# ── Grading Modes ────────────────────────────────────────────
class GradingMode:
    AUTO_GRADE = "auto_grade"
    MATCH_REFERENCE = "match_reference"
    SINGLE_CLIP = "single_clip"

# ── Supported Color Spaces ───────────────────────────────────
KNOWN_COLOR_SPACES = [
    "Rec.709",
    "Rec.709 Gamma 2.4",
    "Rec.2020",
    "DaVinci Wide Gamut",
    "ACES",
    "ACEScg",
    "S-Log3 / S-Gamut3.Cine",
    "V-Log / V-Gamut",
    "Log-C / ARRI Wide Gamut",
    "Canon Log / Cinema Gamut",
    "RED Log3G10 / REDWideGamutRGB",
]
