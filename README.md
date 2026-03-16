# ResolveAI – AI Color Grading Plugin for DaVinci Resolve Studio

An intelligent color grading automation system for DaVinci Resolve Studio. Analyzes your footage, understands each clip's characteristics, and applies adaptive, per-clip color grades automatically.

## Features

- **Intelligent Auto-Grading** – Analyzes all clips on the timeline, computes a baseline, and generates unique CDL corrections per clip
- **Adaptive Per-Clip Grading** – Each clip gets tailored corrections based on its luminance, color temperature, saturation, and contrast
- **Consistency Smoothing** – Ensures cuts between clips feel seamless
- **Multiple Grading Styles** – Balanced, Punchy, Film, Natural
- **Grade Matching** – Match clips to a manually graded reference clip

## Requirements

- **DaVinci Resolve Studio** 18+ (tested on 20.3.2)
- **Python** 3.10+
- **macOS** or **Windows**

## Quick Start

```bash
# Setup
chmod +x setup_env.sh && ./setup_env.sh

# Auto-grade your timeline (Resolve must be running)
source .venv/bin/activate
python main.py --reset --auto

# Try different styles
python main.py --reset --auto --style punchy
python main.py --reset --auto --style film
python main.py --reset --auto --style natural
```

## Architecture

```
Resolve_AI/
├── main.py                    # Entry point & CLI
├── config.py                  # Configuration & constants
├── reset_grades.py            # Reset all clip grades
├── color_engine/
│   ├── auto_grader.py         # Intelligent auto-grading engine
│   ├── analyzer.py            # Frame color analysis
│   ├── frame_grabber.py       # Video frame extraction
│   ├── normalizer.py          # Exposure & WB correction
│   ├── cdl_transform.py       # CDL computation
│   ├── transfer.py            # Color transfer algorithms
│   ├── lut_generator.py       # 3D LUT generation
│   └── look_profiles.py       # Look profile system
├── resolve_bridge/
│   ├── connection.py          # Resolve API connection
│   ├── timeline.py            # Timeline utilities
│   └── grading.py             # Grade application
├── looks/                     # JSON look profiles
├── ui/                        # UI panel
└── tests/                     # Unit tests (52 passing)
```

## How It Works

1. **Phase 1 – Analysis**: Grabs representative frames from each clip, computes color profiles (luminance, RGB distribution, saturation, color temperature)
2. **Phase 2 – Baseline**: Computes median statistics across all clips to establish what "normal" looks like for your project
3. **Phase 3 – Adaptive CDL**: Generates unique CDL corrections for each clip based on how it differs from the baseline and the chosen style
4. **Phase 4 – Consistency**: Smooths extreme outliers so cuts feel natural

## License

MIT
