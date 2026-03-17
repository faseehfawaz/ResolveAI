"""
ResolveAI – Intelligent Auto-Grading Engine

Analyzes ALL clips on the timeline, computes a baseline from the actual
footage, and generates adaptive per-clip corrections that produce
professional-looking, visually consistent grades.

Supports two grading modes:
1. CDL-only: Adaptive per-clip CDL corrections (limited but reliable)
2. DRX + CDL: Apply a professional DRX template for creative grade,
   then use CDL for per-clip normalization (exposure/WB matching)

The system is intelligent:
- It understands each clip's characteristics (luminance, color, saturation)
- It adapts the grade to each clip individually
- It ensures consistency across cuts
- No manual look profile selection needed

Grading Styles:
- "balanced": Clean, professional, neutral corrections
- "punchy":   Strong contrast, deeper blacks, more separation
- "film":     Cinematic desaturation, warm highlights, cool shadows
- "natural":  Minimal correction, preserve the original look
"""

import os
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from color_engine.analyzer import ClipColorProfile, analyze_frames
from color_engine.frame_grabber import grab_frames_from_clip, resize_for_analysis
from color_engine.cdl_transform import format_cdl_for_resolve
from resolve_bridge.timeline import get_all_clips
from resolve_bridge.grading import apply_drx


# ── Grading Style Parameters ────────────────────────────────
# These control HOW MUCH correction to apply, not WHAT correction.
# The actual grade is computed from the footage analysis.

STYLES = {
    "balanced": {
        "contrast_strength": 0.5,    # How much shadow crush
        "color_strength": 0.4,       # How much color correction
        "saturation_target": 0.95,   # Target relative saturation
        "black_point": -0.008,       # How deep blacks go
        "split_tone_strength": 0.3,  # Per-channel power differences
    },
    "punchy": {
        "contrast_strength": 0.8,
        "color_strength": 0.6,
        "saturation_target": 0.88,
        "black_point": -0.015,
        "split_tone_strength": 0.5,
    },
    "film": {
        "contrast_strength": 0.7,
        "color_strength": 0.7,
        "saturation_target": 0.78,
        "black_point": -0.012,
        "split_tone_strength": 0.6,
    },
    "natural": {
        "contrast_strength": 0.2,
        "color_strength": 0.2,
        "saturation_target": 1.0,
        "black_point": -0.003,
        "split_tone_strength": 0.1,
    },
}


@dataclass
class TimelineBaseline:
    """
    Computed baseline statistics across all clips on the timeline.
    This represents "what the footage looks like on average"
    and serves as the normalization target.
    """
    median_luminance: float = 0.0
    median_r_mean: float = 0.0
    median_g_mean: float = 0.0
    median_b_mean: float = 0.0
    median_r_std: float = 0.0
    median_g_std: float = 0.0
    median_b_std: float = 0.0
    median_saturation: float = 0.0
    median_color_temp: float = 0.0
    luminance_range: Tuple[float, float] = (0.0, 1.0)
    num_clips: int = 0


@dataclass
class ClipGrade:
    """
    Computed grade for a single clip.
    """
    clip_name: str = ""
    cdl: Dict = field(default_factory=dict)
    resolve_cdl: Dict = field(default_factory=dict)
    profile: Optional[ClipColorProfile] = None
    deviation_score: float = 0.0  # How far from baseline (0 = identical)


class AutoGrader:
    """
    Intelligent auto-grading engine.

    Usage (CDL-only):
        grader = AutoGrader(style="balanced")
        grader.analyze_timeline()
        grades = grader.compute_grades()
        grader.apply_grades(grades)

    Usage (DRX + CDL normalization):
        grader = AutoGrader(style="balanced", drx_path="/path/to/grade.drx")
        grader.analyze_timeline()
        grades = grader.compute_grades()
        grader.apply_drx_grade(grades)
    """

    def __init__(self, style: str = "balanced", drx_path: str = None):
        if style not in STYLES:
            raise ValueError(f"Unknown style '{style}'. Choose from: {list(STYLES.keys())}")
        self.style = style
        self.style_params = STYLES[style]
        self.profiles: List[ClipColorProfile] = []
        self.clips = []
        self.baseline: Optional[TimelineBaseline] = None
        self.drx_path = drx_path
        self.reference_idx: int = -1  # Index of the reference clip

    def analyze_timeline(self) -> TimelineBaseline:
        """
        Phase 1: Analyze every clip on the timeline.

        Grabs frames, computes color profiles, and derives
        a baseline that represents the timeline's average look.
        """
        print(f"[ResolveAI] ═══ Phase 1: Analyzing Timeline ═══")

        self.clips = get_all_clips()
        if not self.clips:
            raise RuntimeError("No clips found on the timeline.")

        print(f"[ResolveAI] Found {len(self.clips)} clips. Analyzing each...")

        self.profiles = []
        for i, clip in enumerate(self.clips):
            print(f"[ResolveAI]   [{i+1}/{len(self.clips)}] Analyzing '{clip.name}'...")

            frames = grab_frames_from_clip(clip)
            if not frames:
                print(f"[ResolveAI]   ⚠️  Could not grab frames from '{clip.name}', skipping.")
                self.profiles.append(None)
                continue

            frames = resize_for_analysis(frames)
            profile = analyze_frames(frames, clip_name=clip.name)
            self.profiles.append(profile)

            print(f"[ResolveAI]     Lum={profile.luminance_mean:.3f}  "
                  f"RGB=({profile.red.mean:.0f},{profile.green.mean:.0f},{profile.blue.mean:.0f})  "
                  f"Sat={profile.saturation_mean:.3f}  "
                  f"Temp={profile.estimated_color_temp:.0f}K")

        # Compute baseline from all valid profiles
        valid_profiles = [p for p in self.profiles if p is not None]
        if not valid_profiles:
            raise RuntimeError("Could not analyze any clips.")

        self.baseline = self._compute_baseline(valid_profiles)

        print(f"\n[ResolveAI] ═══ Timeline Baseline ═══")
        print(f"[ResolveAI]   Luminance:   {self.baseline.median_luminance:.3f}")
        print(f"[ResolveAI]   RGB means:   ({self.baseline.median_r_mean:.0f}, "
              f"{self.baseline.median_g_mean:.0f}, {self.baseline.median_b_mean:.0f})")
        print(f"[ResolveAI]   Saturation:  {self.baseline.median_saturation:.3f}")
        print(f"[ResolveAI]   Color temp:  {self.baseline.median_color_temp:.0f}K")

        return self.baseline

    def compute_grades(self) -> List[ClipGrade]:
        """
        Phase 2: Compute adaptive CDL corrections for each clip.

        Each clip gets a unique CDL based on:
        1. How it differs from the baseline (normalization)
        2. Its own characteristics (adaptive creative)
        3. The chosen grading style (intensity scaling)
        """
        if self.baseline is None:
            raise RuntimeError("Call analyze_timeline() first.")

        print(f"\n[ResolveAI] ═══ Phase 2: Computing Adaptive Grades ═══")
        print(f"[ResolveAI]   Style: {self.style}")
        if self.drx_path:
            print(f"[ResolveAI]   DRX template: {os.path.basename(self.drx_path)}")

        grades = []
        for i, (clip, profile) in enumerate(zip(self.clips, self.profiles)):
            if profile is None:
                grades.append(None)
                continue

            # Choose CDL computation based on mode
            if self.drx_path:
                # DRX mode: reference-anchored pre-normalization
                cdl = self._compute_reference_cdl(profile, i)
            else:
                # CDL-only mode: full adaptive CDL (normalization + creative)
                cdl = self._compute_adaptive_cdl(profile)

            # Format for Resolve
            resolve_cdl = format_cdl_for_resolve(cdl)

            # Compute deviation score (how different from baseline)
            dev = self._compute_deviation(profile)

            grade = ClipGrade(
                clip_name=clip.name,
                cdl=cdl,
                resolve_cdl=resolve_cdl,
                profile=profile,
                deviation_score=dev,
            )
            grades.append(grade)

            print(f"[ResolveAI]   [{i+1}/{len(self.clips)}] '{clip.name}' "
                  f"→ slope=({cdl['slope'][0]:.3f},{cdl['slope'][1]:.3f},{cdl['slope'][2]:.3f}) "
                  f"offset=({cdl['offset'][0]:.4f},{cdl['offset'][1]:.4f},{cdl['offset'][2]:.4f}) "
                  f"power=({cdl['power'][0]:.3f},{cdl['power'][1]:.3f},{cdl['power'][2]:.3f}) "
                  f"sat={cdl['saturation']:.3f} "
                  f"dev={dev:.3f}")

        # Consistency smoothing
        grades = self._smooth_grades(grades)

        return grades

    def apply_grades(self, grades: List[ClipGrade]) -> int:
        """
        Apply CDL-only grades to clips in Resolve.
        """
        print(f"\n[ResolveAI] ═══ Applying CDL Grades ═══")

        applied = 0
        for i, (clip, grade) in enumerate(zip(self.clips, grades)):
            if grade is None:
                continue

            try:
                result = clip.timeline_item.SetCDL(grade.resolve_cdl)
                if result:
                    print(f"[ResolveAI]   ✅ [{i+1}/{len(self.clips)}] '{clip.name}'")
                    applied += 1
                else:
                    print(f"[ResolveAI]   ❌ [{i+1}/{len(self.clips)}] '{clip.name}' – SetCDL returned False")
            except Exception as e:
                print(f"[ResolveAI]   ❌ [{i+1}/{len(self.clips)}] '{clip.name}' – {e}")

        print(f"\n[ResolveAI] ✅ Done! Applied CDL grades to {applied}/{len(self.clips)} clips.")
        return applied

    def apply_drx_grade(self, grades: List[ClipGrade]) -> int:
        """
        Apply DRX template + reference-anchored CDL normalization.

        This is the intelligent grading path:
        1. Find the REFERENCE CLIP (the one the DRX was designed for)
        2. For each clip: apply CDL that pre-normalizes its raw values
           to match the reference clip's raw values
        3. Apply the DRX template on top — now it "sees" uniform footage

        Result: every clip responds to the DRX identically to the
        reference clip. No manual tuning needed.
        """
        if not self.drx_path or not os.path.isfile(self.drx_path):
            print(f"[ResolveAI] ❌ DRX file not found: {self.drx_path}")
            return 0

        # Find the reference clip (lowest deviation = most representative)
        self._find_reference_clip()
        ref_name = self.clips[self.reference_idx].name if self.reference_idx >= 0 else "unknown"

        print(f"\n[ResolveAI] ═══ Applying DRX + Intelligent Normalization ═══")
        print(f"[ResolveAI]   DRX template: {os.path.basename(self.drx_path)}")
        print(f"[ResolveAI]   Reference clip: '{ref_name}' (DRX was designed for this)")
        print(f"[ResolveAI]   Strategy: Pre-normalize each clip → then apply DRX")

        applied = 0
        for i, (clip, grade) in enumerate(zip(self.clips, grades)):
            if grade is None:
                continue

            try:
                is_ref = (i == self.reference_idx)

                # Step 1: Apply CDL pre-normalization
                cdl_ok = clip.timeline_item.SetCDL(grade.resolve_cdl)

                # Step 2: Apply DRX template on top
                drx_ok = apply_drx(clip.timeline_item, self.drx_path, grade_mode=0)

                if drx_ok:
                    s = grade.cdl["slope"]
                    tag = "REF" if is_ref else f"CDL({s[0]:.3f},{s[1]:.3f},{s[2]:.3f})"
                    print(f"[ResolveAI]   ✅ [{i+1}/{len(self.clips)}] '{clip.name}' [{tag}]")
                    applied += 1
                else:
                    print(f"[ResolveAI]   ❌ [{i+1}/{len(self.clips)}] '{clip.name}' – DRX failed")
            except Exception as e:
                print(f"[ResolveAI]   ❌ [{i+1}/{len(self.clips)}] '{clip.name}' – {e}")

        print(f"\n[ResolveAI] ✅ Done! Applied DRX grades to {applied}/{len(self.clips)} clips.")
        return applied

    def _find_reference_clip(self):
        """
        Find the reference clip — the one the DRX was most likely graded on.

        The reference clip is the one closest to the timeline median (lowest
        deviation score). The DRX was designed for this clip's characteristics,
        so it should get identity CDL (no correction).
        """
        best_idx = 0
        best_dev = float('inf')

        for i, profile in enumerate(self.profiles):
            if profile is None:
                continue
            dev = self._compute_deviation(profile)
            if dev < best_dev:
                best_dev = dev
                best_idx = i

        self.reference_idx = best_idx

    # ── Internal Methods ─────────────────────────────────────

    def _compute_baseline(self, profiles: List[ClipColorProfile]) -> TimelineBaseline:
        """Compute the median statistics across all clip profiles."""
        baseline = TimelineBaseline()
        baseline.num_clips = len(profiles)

        # Use median (robust to outliers) rather than mean
        baseline.median_luminance = float(np.median([p.luminance_mean for p in profiles]))
        baseline.median_r_mean = float(np.median([p.red.mean for p in profiles]))
        baseline.median_g_mean = float(np.median([p.green.mean for p in profiles]))
        baseline.median_b_mean = float(np.median([p.blue.mean for p in profiles]))
        baseline.median_r_std = float(np.median([p.red.std for p in profiles]))
        baseline.median_g_std = float(np.median([p.green.std for p in profiles]))
        baseline.median_b_std = float(np.median([p.blue.std for p in profiles]))
        baseline.median_saturation = float(np.median([p.saturation_mean for p in profiles]))
        baseline.median_color_temp = float(np.median([p.estimated_color_temp for p in profiles]))

        lums = [p.luminance_mean for p in profiles]
        baseline.luminance_range = (min(lums), max(lums))

        return baseline

    def _compute_reference_cdl(self, profile: ClipColorProfile, clip_idx: int) -> Dict:
        """
        Reference-anchored CDL for DRX mode.

        Instead of guessing correction strength, we compute the EXACT CDL
        needed to map this clip's raw values to the reference clip's raw
        values. This way the DRX "sees" identical footage for every clip.

        The reference clip gets identity CDL (no correction).
        Other clips get slope corrections proportional to their RGB
        difference from the reference.

        This is self-correcting — no manual strength parameter to tune.
        """
        # Reference clip gets identity — no correction needed
        if clip_idx == self.reference_idx:
            return {
                "slope": (1.0, 1.0, 1.0),
                "offset": (0.0, 0.0, 0.0),
                "power": (1.0, 1.0, 1.0),
                "saturation": 1.0,
            }

        ref_profile = self.profiles[self.reference_idx]
        if ref_profile is None:
            return {
                "slope": (1.0, 1.0, 1.0),
                "offset": (0.0, 0.0, 0.0),
                "power": (1.0, 1.0, 1.0),
                "saturation": 1.0,
            }

        eps = 1e-6

        # ── SLOPE: Map this clip's RGB to reference's RGB ─────
        # slope = ref_value / clip_value
        # This is the mathematically correct transformation.
        r_slope = ref_profile.red.mean / max(profile.red.mean, eps)
        g_slope = ref_profile.green.mean / max(profile.green.mean, eps)
        b_slope = ref_profile.blue.mean / max(profile.blue.mean, eps)

        # Clamp to safe range (0.80 – 1.25)
        # This prevents extreme corrections on very different clips
        r_slope = max(0.80, min(1.25, r_slope))
        g_slope = max(0.80, min(1.25, g_slope))
        b_slope = max(0.80, min(1.25, b_slope))

        # ── OFFSET: Fine-tune shadows for large exposure gaps ─
        lum_diff = profile.luminance_mean - ref_profile.luminance_mean
        if abs(lum_diff) > 0.08:  # Only for big differences (>8%)
            offset_val = -lum_diff * 0.05  # Very gentle
            offset_val = max(-0.015, min(0.015, offset_val))
        else:
            offset_val = 0.0

        # ── POWER: Identity (DRX handles contrast) ────────────
        # ── SATURATION: Match to reference if very different ──
        sat_ratio = ref_profile.saturation_mean / max(profile.saturation_mean, eps)
        if abs(sat_ratio - 1.0) > 0.3:  # Only if >30% off
            saturation = 1.0 + (sat_ratio - 1.0) * 0.3
            saturation = max(0.75, min(1.25, saturation))
        else:
            saturation = 1.0

        return {
            "slope": (r_slope, g_slope, b_slope),
            "offset": (offset_val, offset_val, offset_val),
            "power": (1.0, 1.0, 1.0),
            "saturation": saturation,
        }

    def _compute_adaptive_cdl(self, profile: ClipColorProfile) -> Dict:
        """
        Compute intelligent CDL corrections for a single clip.

        The corrections are adapted to THIS clip's characteristics,
        not static values from a profile. The grade consists of:

        1. Normalization: bring toward baseline (white balance, exposure)
        2. Contrast: adaptive shadow crush based on clip's own density
        3. Split-tone: per-channel power for color separation
        4. Saturation: adaptive based on original saturation level
        """
        bl = self.baseline
        sp = self.style_params
        eps = 1e-6

        # ── 1. WHITE BALANCE NORMALIZATION (via slope) ────────
        # Bring this clip's RGB balance toward the baseline
        # Only correct channels that differ significantly from baseline
        r_ratio = bl.median_r_mean / max(profile.red.mean, eps)
        g_ratio = bl.median_g_mean / max(profile.green.mean, eps)
        b_ratio = bl.median_b_mean / max(profile.blue.mean, eps)

        # Normalize ratios relative to green (keep green as reference)
        r_norm_slope = r_ratio / max(g_ratio, eps)
        b_norm_slope = b_ratio / max(g_ratio, eps)
        g_norm_slope = 1.0

        # Apply color correction strength
        cs = sp["color_strength"]
        r_slope = 1.0 + (r_norm_slope - 1.0) * cs
        g_slope = 1.0  # Green stays as anchor
        b_slope = 1.0 + (b_norm_slope - 1.0) * cs

        # Clamp slopes
        r_slope = max(0.85, min(1.15, r_slope))
        g_slope = 1.0
        b_slope = max(0.85, min(1.15, b_slope))

        # ── 2. CONTRAST (via power) ──────────────────────────
        # Adaptive: clips that are already contrasty (high std) need
        # less power correction. Flat clips need more.
        clip_contrast = profile.luminance_std  # Higher = more contrast

        # Base power from style
        base_power = 1.0 + sp["contrast_strength"] * 0.3  # 0.3 max additional power

        # Adapt: reduce power for already-contrasty clips
        # If clip_contrast > 0.18 (high contrast), reduce correction
        # If clip_contrast < 0.10 (very flat), increase correction
        contrast_adapt = 1.0
        if clip_contrast > 0.18:
            contrast_adapt = 0.7  # Already contrasty, ease off
        elif clip_contrast < 0.10:
            contrast_adapt = 1.3  # Very flat, push harder

        adaptive_power = 1.0 + (base_power - 1.0) * contrast_adapt

        # ── 3. SPLIT-TONE (per-channel power differences) ────
        # Create per-channel power for color separation in shadows
        # This is the "magic" of CDL grading:
        #   Higher R power → reds pushed into shadows → cooler midtones
        #   Higher B power → blues pushed into shadows → warmer midtones
        st = sp["split_tone_strength"]

        # Determine the clip's color temperature tendency
        # Warm clip (high R/G ratio) → push R power up (cool shadows)
        # Cool clip (high B/G ratio) → push B power up (warm shadows)
        rg_ratio = profile.red.mean / max(profile.green.mean, eps)
        bg_ratio = profile.blue.mean / max(profile.green.mean, eps)

        # Split-tone: complementary correction
        r_power_shift = (rg_ratio - 1.0) * st * 0.3  # Warm → push R into shadows
        b_power_shift = (1.0 - bg_ratio) * st * 0.3  # Cool → push B into shadows

        r_power = adaptive_power + r_power_shift
        g_power = adaptive_power
        b_power = adaptive_power - b_power_shift

        # Clamp power
        r_power = max(0.85, min(1.35, r_power))
        g_power = max(0.85, min(1.35, g_power))
        b_power = max(0.85, min(1.35, b_power))

        # ── 4. BLACK POINT (via offset) ──────────────────────
        # Negative offset deepens blacks. Adapt based on how
        # much shadow detail the clip already has.
        base_offset = sp["black_point"]

        # If clip is already dark (low luminance), use less negative offset
        # If clip is bright, push blacks down more
        lum_factor = profile.luminance_mean / max(bl.median_luminance, eps)
        if lum_factor > 1.1:
            # Brighter than average → deeper blacks
            offset_scale = 1.2
        elif lum_factor < 0.9:
            # Darker than average → gentler blacks
            offset_scale = 0.7
        else:
            offset_scale = 1.0

        r_offset = base_offset * offset_scale
        g_offset = base_offset * offset_scale
        b_offset = base_offset * offset_scale * 0.8  # Slightly less on blue

        # ── 5. SATURATION ────────────────────────────────────
        target_sat = sp["saturation_target"]

        # Adapt: if clip is already desaturated, don't desaturate further
        if profile.saturation_mean < 0.15:
            # Low saturation footage → preserve what's there
            saturation = max(target_sat, 0.95)
        elif profile.saturation_mean > 0.4:
            # Highly saturated → pull back more
            saturation = target_sat * 0.95
        else:
            saturation = target_sat

        return {
            "slope": (r_slope, g_slope, b_slope),
            "offset": (r_offset, g_offset, b_offset),
            "power": (r_power, g_power, b_power),
            "saturation": saturation,
        }

    def _compute_deviation(self, profile: ClipColorProfile) -> float:
        """How far is this clip from the baseline? (0 = identical)"""
        bl = self.baseline
        lum_dev = abs(profile.luminance_mean - bl.median_luminance) / max(bl.median_luminance, 0.01)
        r_dev = abs(profile.red.mean - bl.median_r_mean) / max(bl.median_r_mean, 1.0)
        g_dev = abs(profile.green.mean - bl.median_g_mean) / max(bl.median_g_mean, 1.0)
        b_dev = abs(profile.blue.mean - bl.median_b_mean) / max(bl.median_b_mean, 1.0)
        return float(np.mean([lum_dev, r_dev, g_dev, b_dev]))

    def _smooth_grades(self, grades: List[Optional[ClipGrade]]) -> List[Optional[ClipGrade]]:
        """
        Consistency pass: smooth CDL values across clips to avoid
        jarring changes between cuts.

        If any clip's CDL is very different from its neighbors,
        blend it toward the average to maintain visual consistency.
        """
        valid = [(i, g) for i, g in enumerate(grades) if g is not None]
        if len(valid) < 3:
            return grades  # Too few clips to smooth

        # Compute average CDL across all clips
        avg_slope = [0.0, 0.0, 0.0]
        avg_offset = [0.0, 0.0, 0.0]
        avg_power = [0.0, 0.0, 0.0]
        n = len(valid)

        for _, g in valid:
            for c in range(3):
                avg_slope[c] += g.cdl["slope"][c] / n
                avg_offset[c] += g.cdl["offset"][c] / n
                avg_power[c] += g.cdl["power"][c] / n

        # If any clip's CDL deviates too much from average, blend toward average
        BLEND_THRESHOLD = 0.15  # 15% deviation triggers smoothing
        BLEND_AMOUNT = 0.3      # Blend 30% toward average

        for idx, grade in valid:
            needs_smoothing = False
            for c in range(3):
                if abs(grade.cdl["slope"][c] - avg_slope[c]) / max(abs(avg_slope[c]), 0.01) > BLEND_THRESHOLD:
                    needs_smoothing = True
                if abs(grade.cdl["power"][c] - avg_power[c]) / max(abs(avg_power[c]), 0.01) > BLEND_THRESHOLD:
                    needs_smoothing = True

            if needs_smoothing:
                smoothed_slope = tuple(
                    grade.cdl["slope"][c] * (1 - BLEND_AMOUNT) + avg_slope[c] * BLEND_AMOUNT
                    for c in range(3)
                )
                smoothed_offset = tuple(
                    grade.cdl["offset"][c] * (1 - BLEND_AMOUNT) + avg_offset[c] * BLEND_AMOUNT
                    for c in range(3)
                )
                smoothed_power = tuple(
                    grade.cdl["power"][c] * (1 - BLEND_AMOUNT) + avg_power[c] * BLEND_AMOUNT
                    for c in range(3)
                )

                grade.cdl["slope"] = smoothed_slope
                grade.cdl["offset"] = smoothed_offset
                grade.cdl["power"] = smoothed_power
                grade.resolve_cdl = format_cdl_for_resolve(grade.cdl)

        return grades
