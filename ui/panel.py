"""
ResolveAI – Plugin UI Panel

Builds the plugin's user interface using DaVinci Resolve's UIManager (Qt-based).
This provides an integrated panel within Resolve Studio.

For environments where UIManager is not available (e.g., testing outside Resolve),
a basic command-line fallback interface is provided.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DEFAULT_LOOK, DEFAULT_INTENSITY, DEFAULT_MODE, GradingMode
from color_engine.look_profiles import list_available_looks


def build_ui(resolve, dispatcher_fn):
    """
    Build and display the ResolveAI plugin UI panel.
    
    Uses Resolve's UIManager if available (Studio version).
    Falls back to a CLI interface if UIManager is unavailable.
    
    Args:
        resolve: The DaVinci Resolve scripting API object.
        dispatcher_fn: Callback function that receives UI events:
            dispatcher_fn(action, params) where:
            - action: "apply_grade", "undo", "set_reference", etc.
            - params: dict with grade parameters.
    
    Returns:
        The UI window object (or None for CLI mode).
    """
    try:
        fusion = resolve.Fusion()
        ui = fusion.UIManager
        disp = fusion.UIDispatcher
        return _build_resolve_ui(ui, disp, dispatcher_fn)
    except Exception as e:
        print(f"[ResolveAI] UIManager not available ({e})")
        print("[ResolveAI] Falling back to command-line interface.")
        return None


def _build_resolve_ui(ui, disp, dispatcher_fn):
    """Build the Qt-based UI using Resolve's UIManager."""

    available_looks = list_available_looks()
    look_display_names = {
        "corporate": "Corporate / Professional",
        "cinematic": "Cinematic / Film",
        "warm_natural": "Warm & Natural",
        "cool_desaturated": "Cool & Desaturated",
    }

    # ── Window Definition ────────────────────────────────────
    win = disp.AddWindow(
        {
            "ID": "ResolveAI",
            "WindowTitle": "ResolveAI – AI Color Grading",
            "Geometry": [100, 100, 420, 580],
            "Spacing": 10,
        },
        [
            # ── Header ───────────────────────────────────────
            ui.VGroup(
                {"Spacing": 5},
                [
                    ui.Label(
                        {
                            "ID": "HeaderLabel",
                            "Text": "🎨  ResolveAI Color Grading",
                            "Alignment": {"AlignHCenter": True},
                            "Font": ui.Font({"PixelSize": 18, "Bold": True}),
                        }
                    ),
                    ui.Label(
                        {
                            "ID": "SubHeaderLabel",
                            "Text": "AI-powered automatic color grading",
                            "Alignment": {"AlignHCenter": True},
                            "Font": ui.Font({"PixelSize": 11}),
                        }
                    ),
                ],
            ),
            # ── Separator ────────────────────────────────────
            ui.Label({"Text": "─" * 55}),

            # ── Mode Selector ────────────────────────────────
            ui.VGroup(
                {"Spacing": 5},
                [
                    ui.Label({"Text": "Grading Mode:", "Font": ui.Font({"Bold": True})}),
                    ui.ComboBox(
                        {
                            "ID": "ModeCombo",
                            "Items": [
                                "Auto-Grade to Look",
                                "Match from Reference Clip",
                                "Grade Single Clip",
                            ],
                        }
                    ),
                ],
            ),

            # ── Look Selector ────────────────────────────────
            ui.VGroup(
                {"Spacing": 5},
                [
                    ui.Label({"Text": "Look / Style:", "Font": ui.Font({"Bold": True})}),
                    ui.ComboBox(
                        {
                            "ID": "LookCombo",
                            "Items": [
                                look_display_names.get(l, l.replace("_", " ").title())
                                for l in available_looks
                            ],
                        }
                    ),
                ],
            ),

            # ── Transfer Method ──────────────────────────────
            ui.VGroup(
                {"Spacing": 5},
                [
                    ui.Label({"Text": "Transfer Method:", "Font": ui.Font({"Bold": True})}),
                    ui.ComboBox(
                        {
                            "ID": "MethodCombo",
                            "Items": [
                                "Reinhard (Recommended)",
                                "Histogram Matching",
                                "MVGD (Advanced)",
                            ],
                        }
                    ),
                ],
            ),

            # ── Intensity Slider ─────────────────────────────
            ui.VGroup(
                {"Spacing": 5},
                [
                    ui.Label({"Text": "Intensity:", "Font": ui.Font({"Bold": True})}),
                    ui.HGroup(
                        {"Spacing": 10},
                        [
                            ui.Slider(
                                {
                                    "ID": "IntensitySlider",
                                    "Minimum": 0,
                                    "Maximum": 100,
                                    "Value": DEFAULT_INTENSITY,
                                }
                            ),
                            ui.Label(
                                {
                                    "ID": "IntensityLabel",
                                    "Text": f"{DEFAULT_INTENSITY}%",
                                    "MinimumSize": [40, 0],
                                }
                            ),
                        ],
                    ),
                ],
            ),

            # ── Reference Clip ───────────────────────────────
            ui.VGroup(
                {"Spacing": 5},
                [
                    ui.Label(
                        {
                            "ID": "RefLabel",
                            "Text": "Reference Clip:",
                            "Font": ui.Font({"Bold": True}),
                        }
                    ),
                    ui.HGroup(
                        {"Spacing": 10},
                        [
                            ui.Label(
                                {
                                    "ID": "RefClipName",
                                    "Text": "(none selected)",
                                    "StyleSheet": "color: #888;",
                                }
                            ),
                            ui.Button(
                                {
                                    "ID": "SetRefButton",
                                    "Text": "Set Current Clip as Reference",
                                }
                            ),
                        ],
                    ),
                ],
            ),
            # ── Separator ────────────────────────────────────
            ui.Label({"Text": "─" * 55}),

            # ── Action Buttons ───────────────────────────────
            ui.HGroup(
                {"Spacing": 10},
                [
                    ui.Button(
                        {
                            "ID": "ApplyButton",
                            "Text": "✨ Apply Grade",
                            "Font": ui.Font({"Bold": True, "PixelSize": 14}),
                            "MinimumSize": [200, 40],
                        }
                    ),
                    ui.Button(
                        {
                            "ID": "UndoButton",
                            "Text": "↩ Undo",
                            "MinimumSize": [80, 40],
                        }
                    ),
                ],
            ),

            # ── Progress ─────────────────────────────────────
            ui.VGroup(
                {"Spacing": 5},
                [
                    ui.ProgressBar(
                        {
                            "ID": "ProgressBar",
                            "Value": 0,
                            "Maximum": 100,
                        }
                    ),
                    ui.Label(
                        {
                            "ID": "StatusLabel",
                            "Text": "Ready",
                            "StyleSheet": "color: #aaa;",
                            "Alignment": {"AlignHCenter": True},
                        }
                    ),
                ],
            ),
        ],
    )

    # ── UI State ─────────────────────────────────────────────
    itm = win.GetItems()

    # ── Event Handlers ───────────────────────────────────────
    def on_intensity_changed(ev):
        val = itm["IntensitySlider"].Value
        itm["IntensityLabel"].Text = f"{val}%"

    def on_apply(ev):
        mode_idx = itm["ModeCombo"].CurrentIndex
        modes = [GradingMode.AUTO_GRADE, GradingMode.MATCH_REFERENCE, GradingMode.SINGLE_CLIP]
        mode = modes[mode_idx]

        look_idx = itm["LookCombo"].CurrentIndex
        look_name = available_looks[look_idx] if look_idx < len(available_looks) else DEFAULT_LOOK

        method_idx = itm["MethodCombo"].CurrentIndex
        methods = ["reinhard", "histogram", "mvgd"]
        method = methods[method_idx]

        intensity = itm["IntensitySlider"].Value / 100.0

        dispatcher_fn("apply_grade", {
            "mode": mode,
            "look": look_name,
            "method": method,
            "intensity": intensity,
        })

    def on_undo(ev):
        dispatcher_fn("undo", {})

    def on_set_reference(ev):
        dispatcher_fn("set_reference", {})

    def on_close(ev):
        disp.ExitLoop()

    # ── Connect Events ───────────────────────────────────────
    win.On.ResolveAI.Close = on_close
    win.On.IntensitySlider.ValueChanged = on_intensity_changed
    win.On.ApplyButton.Clicked = on_apply
    win.On.UndoButton.Clicked = on_undo
    win.On.SetRefButton.Clicked = on_set_reference

    return win, disp, itm


def update_progress(itm, progress: int, status: str = ""):
    """Update the progress bar and status text in the UI."""
    try:
        if itm and "ProgressBar" in itm:
            itm["ProgressBar"].Value = progress
        if itm and "StatusLabel" in itm and status:
            itm["StatusLabel"].Text = status
    except Exception:
        pass


def update_reference_clip(itm, clip_name: str):
    """Update the reference clip display in the UI."""
    try:
        if itm and "RefClipName" in itm:
            itm["RefClipName"].Text = clip_name
            itm["RefClipName"].StyleSheet = "color: #4CAF50; font-weight: bold;"
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# CLI INTERFACE (Fallback when UIManager is unavailable)
# ═══════════════════════════════════════════════════════════════

def run_cli_interface(dispatcher_fn):
    """
    Run a simple command-line interface for the plugin.
    
    This is used when running outside of DaVinci Resolve or
    when the UIManager is not available.
    """
    available_looks = list_available_looks()

    print("\n")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       🎨  ResolveAI – AI Color Grading Plugin          ║")
    print("║          Command-Line Interface                        ║")
    print("╚══════════════════════════════════════════════════════════╝")

    while True:
        print("\n─── Grading Modes ─────────────────────────")
        print("  1. Auto-Grade to Look")
        print("  2. Match from Reference Clip")
        print("  3. Grade Single Clip (at playhead)")
        print("  4. Show Timeline Info")
        print("  5. Quit")
        print()

        choice = input("  Select mode (1-5): ").strip()

        if choice == "5":
            print("[ResolveAI] Goodbye!")
            break

        elif choice == "4":
            dispatcher_fn("show_info", {})
            continue

        elif choice in ("1", "2", "3"):
            modes = {
                "1": GradingMode.AUTO_GRADE,
                "2": GradingMode.MATCH_REFERENCE,
                "3": GradingMode.SINGLE_CLIP,
            }
            mode = modes[choice]

            # Select look
            print("\n─── Available Looks ────────────────────────")
            for i, look in enumerate(available_looks):
                print(f"  {i+1}. {look.replace('_', ' ').title()}")

            look_choice = input(f"\n  Select look (1-{len(available_looks)}): ").strip()
            try:
                look_idx = int(look_choice) - 1
                look_name = available_looks[look_idx]
            except (ValueError, IndexError):
                look_name = DEFAULT_LOOK
                print(f"  Using default: {look_name}")

            # Select method
            print("\n─── Transfer Methods ──────────────────────")
            print("  1. Reinhard (Recommended)")
            print("  2. Histogram Matching")
            print("  3. MVGD (Advanced)")

            method_choice = input("\n  Select method (1-3) [1]: ").strip()
            methods = {"1": "reinhard", "2": "histogram", "3": "mvgd"}
            method = methods.get(method_choice, "reinhard")

            # Intensity
            intensity_str = input("\n  Intensity (0-100) [100]: ").strip()
            try:
                intensity = int(intensity_str) / 100.0
            except ValueError:
                intensity = 1.0

            # If match reference, select reference first
            if mode == GradingMode.MATCH_REFERENCE:
                print("\n  [!] Navigate to your reference clip in Resolve, then press Enter.")
                input("      Press Enter when ready...")
                dispatcher_fn("set_reference", {})

            # Apply
            dispatcher_fn("apply_grade", {
                "mode": mode,
                "look": look_name,
                "method": method,
                "intensity": intensity,
            })

        else:
            print("  Invalid choice. Try again.")
