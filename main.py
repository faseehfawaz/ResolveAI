#!/usr/bin/env python3
"""
ResolveAI – AI Color Grading Plugin for DaVinci Resolve Studio

Main entry point. This script can be run as:
1. A Workflow Integration Plugin inside DaVinci Resolve Studio
2. A standalone script (connects to a running Resolve instance)

Usage:
    # From within Resolve's script console or as a Workflow Integration:
    python main.py

    # From the command line (Resolve must be running):
    python main.py --cli
"""

import sys
import os
import argparse
import traceback

# ── Ensure project root is on sys.path ──────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import GradingMode, DEFAULT_TRANSFER_METHOD, PLUGIN_NAME, PLUGIN_VERSION
from resolve_bridge.connection import get_connection
from resolve_bridge.timeline import (
    get_all_clips, get_clip_at_playhead, print_timeline_summary, ClipInfo
)
from resolve_bridge.grading import apply_cdl, apply_lut
from color_engine.frame_grabber import (
    grab_frames_from_clip, resize_for_analysis
)
from color_engine.analyzer import analyze_frames, ClipColorProfile, print_profile_summary
from color_engine.look_profiles import load_look_profile, LookProfile
from color_engine.cdl_transform import (
    cdl_for_look_profile,
    cdl_for_reference_match,
    format_cdl_for_resolve,
)
from color_engine.auto_grader import AutoGrader, STYLES


# ═══════════════════════════════════════════════════════════════
# GRADING ENGINE – Orchestrates the full CDL-based pipeline
# ═══════════════════════════════════════════════════════════════

class GradingEngine:
    """
    Main orchestrator for the AI color grading pipeline.
    
    Pipeline (CDL-based, confirmed working with Resolve Studio 20.3):
    1. Analyze clips (grab frames → extract color profiles)
    2. Compute normalization CDL (exposure + WB corrections)
    3. Compute creative CDL (look profile or reference match)
    4. Combine into a single CDL
    5. Apply via SetCDL API (confirmed working)
    """

    def __init__(self):
        self.connection = None
        self.reference_profile: ClipColorProfile = None
        self.reference_clip_name: str = ""
        self.clip_profiles: dict = {}
        self.last_applied_clips: list = []
        self._progress_callback = None

    def set_progress_callback(self, callback):
        """Set a callback: callback(progress_pct, status_msg)"""
        self._progress_callback = callback

    def _progress(self, pct: int, msg: str):
        print(f"[ResolveAI] [{pct:3d}%] {msg}")
        if self._progress_callback:
            self._progress_callback(pct, msg)

    # ── Connection ───────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to DaVinci Resolve using the shared singleton."""
        self.connection = get_connection()
        return self.connection._resolve is not None

    # ── Reference Clip ───────────────────────────────────────

    def set_reference_from_playhead(self) -> bool:
        """
        Set the reference clip from the clip at the playhead.
        Analyzes it immediately and stores the profile.
        """
        clip = get_clip_at_playhead()
        if clip is None:
            print("[ResolveAI] No clip at playhead. Navigate to a clip and try again.")
            return False

        self._progress(10, f"Analyzing reference clip: {clip.name}")
        profile = self._analyze_clip(clip)
        if profile is None:
            return False

        self.reference_profile = profile
        self.reference_clip_name = clip.name

        print_profile_summary(self.reference_profile)
        self._progress(100, f"Reference set: {clip.name}")
        return True

    # ── Auto-Grade to Look ───────────────────────────────────

    def auto_grade_to_look(
        self,
        look_name: str,
        method: str = None,
        intensity: float = 1.0,
    ) -> int:
        """
        Auto-grade all timeline clips to match a predefined look.
        
        Returns:
            Number of clips successfully graded.
        """
        self._progress(0, "Loading look profile...")

        try:
            look_profile = load_look_profile(look_name)
        except FileNotFoundError:
            print(f"[ResolveAI] Look profile '{look_name}' not found.")
            return 0

        self._progress(5, "Collecting timeline clips...")
        clips = get_all_clips()
        if not clips:
            print("[ResolveAI] No clips found on timeline.")
            return 0

        total = len(clips)
        graded = 0

        for i, clip in enumerate(clips):
            pct = int(10 + (i / total) * 85)
            self._progress(pct, f"Grading clip {i+1}/{total}: {clip.name}")

            try:
                success = self._apply_look_to_clip(clip, look_profile, intensity)
                if success:
                    graded += 1
            except Exception as e:
                print(f"[ResolveAI] Error grading '{clip.name}': {e}")
                traceback.print_exc()

        self._progress(100, f"Done! Graded {graded}/{total} clips with '{look_name}' look.")
        self.last_applied_clips = clips
        return graded

    # ── Match from Reference ─────────────────────────────────

    def match_from_reference(
        self,
        method: str = None,
        intensity: float = 1.0,
    ) -> int:
        """
        Match all timeline clips to the reference clip's color grade.
        
        Returns:
            Number of clips successfully matched.
        """
        if self.reference_profile is None:
            print("[ResolveAI] No reference clip set. Set a reference first.")
            return 0

        self._progress(5, "Collecting timeline clips...")
        clips = get_all_clips()
        if not clips:
            return 0

        total = len(clips)
        graded = 0

        for i, clip in enumerate(clips):
            if clip.name == self.reference_clip_name:
                self._progress(int(10 + (i / total) * 85),
                             f"Skipping reference clip: {clip.name}")
                continue

            pct = int(10 + (i / total) * 85)
            self._progress(pct, f"Matching clip {i+1}/{total}: {clip.name}")

            try:
                success = self._match_clip_to_reference(clip, intensity)
                if success:
                    graded += 1
            except Exception as e:
                print(f"[ResolveAI] Error matching '{clip.name}': {e}")
                traceback.print_exc()

        self._progress(100, f"Done! Matched {graded}/{total} clips to reference.")
        self.last_applied_clips = clips
        return graded

    # ── Grade Single Clip ────────────────────────────────────

    def grade_single_clip(
        self,
        look_name: str,
        method: str = None,
        intensity: float = 1.0,
    ) -> bool:
        """Grade only the clip at the current playhead."""
        clip = get_clip_at_playhead()
        if clip is None:
            print("[ResolveAI] No clip at playhead.")
            return False

        try:
            look_profile = load_look_profile(look_name)
        except FileNotFoundError:
            print(f"[ResolveAI] Look profile '{look_name}' not found.")
            return False

        self._progress(20, f"Grading clip: {clip.name}")
        success = self._apply_look_to_clip(clip, look_profile, intensity)

        if success:
            self._progress(100, f"Graded '{clip.name}' with '{look_name}' look.")
        else:
            self._progress(100, f"Failed to grade '{clip.name}'.")

        return success

    # ── Internal: Analyze ────────────────────────────────────

    def _analyze_clip(self, clip: ClipInfo) -> ClipColorProfile:
        """Grab frames and analyze a clip's color profile."""
        frames = grab_frames_from_clip(clip)
        if not frames:
            print(f"[ResolveAI] Could not grab frames from '{clip.name}'")
            return None

        frames = resize_for_analysis(frames)
        profile = analyze_frames(frames, clip_name=clip.name)
        self.clip_profiles[clip.name] = profile
        return profile

    # ── Internal: Apply Look via CDL ─────────────────────────

    def _apply_look_to_clip(
        self,
        clip: ClipInfo,
        look_profile: LookProfile,
        intensity: float,
    ) -> bool:
        """
        Full CDL-based grading pipeline for a single clip.
        
        Steps:
        1. Grab & analyze frames
        2. Compute combined CDL (normalization + creative)
        3. Apply CDL via Resolve API
        """
        # Step 1: Analyze
        profile = self._analyze_clip(clip)
        if profile is None:
            return False

        # Step 2: Compute combined CDL
        cdl = cdl_for_look_profile(look_profile, profile)

        # Apply intensity blending
        if intensity < 1.0:
            cdl = _blend_cdl_with_identity(cdl, intensity)

        # Step 3: Apply to Resolve via SetCDL
        return self._apply_cdl_to_clip(clip, cdl)

    # ── Internal: Match to Reference via CDL ─────────────────

    def _match_clip_to_reference(
        self,
        clip: ClipInfo,
        intensity: float,
    ) -> bool:
        """Match a single clip to the reference profile via CDL."""
        # Step 1: Analyze
        profile = self._analyze_clip(clip)
        if profile is None:
            return False

        # Step 2: Compute CDL for reference matching
        cdl = cdl_for_reference_match(profile, self.reference_profile, intensity)

        # Step 3: Apply
        return self._apply_cdl_to_clip(clip, cdl)

    # ── Internal: Apply CDL to Resolve ───────────────────────

    def _apply_cdl_to_clip(self, clip: ClipInfo, cdl: dict) -> bool:
        """Apply a computed CDL to a clip in Resolve."""
        item = clip.timeline_item
        resolve_cdl = format_cdl_for_resolve(cdl, node_index=1)

        try:
            result = item.SetCDL(resolve_cdl)
            if result:
                s = cdl["slope"]
                o = cdl["offset"]
                print(f"[ResolveAI] ✅ Applied CDL to '{clip.name}' "
                      f"(slope: R{s[0]:.2f} G{s[1]:.2f} B{s[2]:.2f}, "
                      f"offset: R{o[0]:.3f} G{o[1]:.3f} B{o[2]:.3f})")
                return True
            else:
                print(f"[ResolveAI] ⚠️  SetCDL returned False for '{clip.name}'")
                return False
        except Exception as e:
            print(f"[ResolveAI] Error applying CDL to '{clip.name}': {e}")
            return False


# ═══════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════

def _blend_cdl_with_identity(cdl: dict, intensity: float) -> dict:
    """Blend a CDL with identity (no-change) CDL based on intensity."""
    def lerp(a, b, t):
        return a + (b - a) * t

    return {
        "slope": tuple(lerp(1.0, s, intensity) for s in cdl["slope"]),
        "offset": tuple(lerp(0.0, o, intensity) for o in cdl["offset"]),
        "power": tuple(lerp(1.0, p, intensity) for p in cdl["power"]),
        "saturation": lerp(1.0, cdl.get("saturation", 1.0), intensity),
    }


# ═══════════════════════════════════════════════════════════════
# UI DISPATCHER – Handles UI events
# ═══════════════════════════════════════════════════════════════

_engine = GradingEngine()


def dispatch_action(action: str, params: dict):
    """
    Handle actions from the UI (either Qt or CLI).
    Bridge between the UI layer and the GradingEngine.
    """
    global _engine

    if action == "apply_grade":
        mode = params.get("mode", GradingMode.AUTO_GRADE)
        look = params.get("look", "corporate")
        method = params.get("method", DEFAULT_TRANSFER_METHOD)
        intensity = params.get("intensity", 1.0)

        print(f"\n[ResolveAI] ═══ Starting Grade ═══")
        print(f"  Mode: {mode}")
        print(f"  Look: {look}")
        print(f"  Method: CDL-based (optimized for Resolve Studio)")
        print(f"  Intensity: {intensity * 100:.0f}%\n")

        if mode == GradingMode.AUTO_GRADE:
            result = _engine.auto_grade_to_look(look, method, intensity)
            print(f"\n[ResolveAI] Auto-graded {result} clips.")

        elif mode == GradingMode.MATCH_REFERENCE:
            if _engine.reference_profile is None:
                print("[ResolveAI] Please set a reference clip first!")
                return
            result = _engine.match_from_reference(method, intensity)
            print(f"\n[ResolveAI] Matched {result} clips to reference.")

        elif mode == GradingMode.SINGLE_CLIP:
            result = _engine.grade_single_clip(look, method, intensity)
            print(f"\n[ResolveAI] Single clip grade: {'success' if result else 'failed'}.")

    elif action == "set_reference":
        _engine.set_reference_from_playhead()

    elif action == "undo":
        print("[ResolveAI] Undo: use Ctrl+Z / Cmd+Z in Resolve.")

    elif action == "show_info":
        print_timeline_summary()


# ═══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    """Main entry point for the ResolveAI plugin."""
    parser = argparse.ArgumentParser(
        description=f"{PLUGIN_NAME} v{PLUGIN_VERSION} – AI Color Grading Plugin"
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Force command-line interface (skip UIManager)"
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Auto-grade entire timeline intelligently (analyzes all clips)"
    )
    parser.add_argument(
        "--style", type=str, default="balanced",
        choices=list(STYLES.keys()),
        help="Grading style: balanced, punchy, film, natural (default: balanced)"
    )
    parser.add_argument(
        "--look", type=str, default=None,
        help="[Legacy] Apply a static look profile instead of intelligent grading"
    )
    parser.add_argument(
        "--method", type=str, default="reinhard",
        choices=["reinhard", "histogram", "mvgd"],
        help="Color transfer method for legacy mode (default: reinhard)"
    )
    parser.add_argument(
        "--drx", type=str, default=None,
        help="Path to a .drx grade template file (applies professional grade from Resolve)"
    )
    parser.add_argument(
        "--intensity", type=float, default=1.0,
        help="Grade intensity 0.0–1.0 (default: 1.0)"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Reset all clip grades to default before grading"
    )

    args = parser.parse_args()

    print(f"\n  {PLUGIN_NAME} v{PLUGIN_VERSION}")
    print(f"  {'─' * 40}\n")

    # Connect to Resolve
    if not _engine.connect():
        print("\n[ResolveAI] Could not connect to DaVinci Resolve.")
        print("  Make sure DaVinci Resolve Studio is running.")
        sys.exit(1)

    # Reset mode
    if args.reset:
        from reset_grades import main as reset_main
        reset_main()
        if not args.auto and not args.look and not args.drx:
            sys.exit(0)

    # Auto-find DRX if --drx given without path
    drx_path = args.drx
    if drx_path == "auto" or (args.auto and drx_path is None):
        # Auto-search for DRX files in samplestills/
        stills_dir = os.path.join(PROJECT_ROOT, "samplestills")
        if os.path.isdir(stills_dir):
            drx_files = [f for f in os.listdir(stills_dir) if f.endswith(".drx")]
            if drx_files:
                drx_path = os.path.join(stills_dir, drx_files[0])
                print(f"[ResolveAI] Found DRX template: {drx_files[0]}")

    # Auto mode – intelligent grading
    if args.auto:
        if args.look:
            # Legacy: use static look profile
            result = _engine.auto_grade_to_look(args.look, args.method, args.intensity)
            print(f"\n[ResolveAI] Auto-graded {result} clips with '{args.look}' look. Done.")
        else:
            # Intelligent auto-grading with optional DRX template
            grader = AutoGrader(style=args.style, drx_path=drx_path)

            # Phase 1: Analyze
            grader.analyze_timeline()

            # Phase 2: Compute adaptive grades
            grades = grader.compute_grades()

            # Phase 3: Apply
            if drx_path and os.path.isfile(drx_path):
                grader.apply_drx_grade(grades)
            else:
                grader.apply_grades(grades)

        sys.exit(0)

    # Interactive mode
    if args.cli:
        from ui.panel import run_cli_interface
        run_cli_interface(dispatch_action)
    else:
        from ui.panel import build_ui, run_cli_interface
        try:
            resolve = _engine.connection.resolve
            result = build_ui(resolve, dispatch_action)
            if result is not None:
                win, disp, itm = result
                win.Show()
                disp.RunLoop()
                win.Hide()
            else:
                run_cli_interface(dispatch_action)
        except Exception as e:
            print(f"[ResolveAI] UI error: {e}")
            run_cli_interface(dispatch_action)


if __name__ == "__main__":
    main()
