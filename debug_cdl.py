#!/usr/bin/env python3
"""
ResolveAI – Debug: Print clip analysis and computed CDL values.

Shows exactly what luminance/color values the analyzer computes,
what CDL corrections are generated, and helps identify why clips
are being overexposed.
"""

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from resolve_bridge.connection import get_connection
from resolve_bridge.timeline import get_all_clips
from color_engine.frame_grabber import grab_frames_from_clip, resize_for_analysis
from color_engine.analyzer import analyze_frames, print_profile_summary
from color_engine.normalizer import compute_normalization_for_profile
from color_engine.look_profiles import load_look_profile
from color_engine.cdl_transform import cdl_for_look_profile, format_cdl_for_resolve


def main():
    print("\n╔══════════════════════════════════════════════════╗")
    print("║  ResolveAI – CDL Debug Analysis                 ║")
    print("╚══════════════════════════════════════════════════╝\n")

    conn = get_connection()
    if conn._resolve is None:
        print("❌ Could not connect to Resolve.")
        return

    look = load_look_profile("corporate")
    print(f"📋 Look Profile: {look.display_name}")
    print(f"   target_luminance: {look.target_luminance}")
    print(f"   target_temp:      {look.target_temp}")
    print(f"   contrast:         {look.contrast}")
    print(f"   shadow_lift:      {look.shadow_lift}")
    print(f"   slope_adjust:     {look.slope_adjust}")
    print(f"   offset_adjust:    {look.offset_adjust}")
    print(f"   saturation:       {look.saturation_multiplier}")

    clips = get_all_clips()
    if not clips:
        print("❌ No clips found.")
        return

    for i, clip in enumerate(clips):
        print(f"\n{'═'*50}")
        print(f"🎞  Clip {i+1}: {clip.name}")
        print(f"{'═'*50}")

        frames = grab_frames_from_clip(clip)
        if not frames:
            print("  ❌ Could not grab frames")
            continue

        frames = resize_for_analysis(frames)
        profile = analyze_frames(frames, clip_name=clip.name)

        print(f"\n  📊 Analyzed Profile:")
        print(f"     luminance_mean:  {profile.luminance_mean:.4f}")
        print(f"     luminance_std:   {profile.luminance_std:.4f}")
        print(f"     R mean/std:      {profile.red.mean:.1f} / {profile.red.std:.1f}")
        print(f"     G mean/std:      {profile.green.mean:.1f} / {profile.green.std:.1f}")
        print(f"     B mean/std:      {profile.blue.mean:.1f} / {profile.blue.std:.1f}")
        print(f"     saturation_mean: {profile.saturation_mean:.4f}")
        print(f"     color_temp:      {profile.estimated_color_temp:.0f}K")

        # Compute normalization CDL
        norm_cdl = compute_normalization_for_profile(
            profile,
            target_luminance=look.target_luminance,
            target_temp=look.target_temp,
        )
        print(f"\n  🔧 Normalization CDL:")
        print(f"     slope:  {norm_cdl['slope']}")
        print(f"     offset: {norm_cdl['offset']}")
        print(f"     power:  {norm_cdl['power']}")

        # Compute combined CDL
        combined_cdl = cdl_for_look_profile(look, profile)
        print(f"\n  🎨 Combined CDL (norm + creative):")
        print(f"     slope:      {tuple(f'{v:.4f}' for v in combined_cdl['slope'])}")
        print(f"     offset:     {tuple(f'{v:.4f}' for v in combined_cdl['offset'])}")
        print(f"     power:      {tuple(f'{v:.4f}' for v in combined_cdl['power'])}")
        print(f"     saturation: {combined_cdl['saturation']:.4f}")

        # Format for Resolve
        resolve_cdl = format_cdl_for_resolve(combined_cdl)
        print(f"\n  📤 Resolve SetCDL payload:")
        for k, v in resolve_cdl.items():
            print(f"     {k}: {v}")

    print()


if __name__ == "__main__":
    main()
