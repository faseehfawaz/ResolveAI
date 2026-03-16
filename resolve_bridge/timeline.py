"""
ResolveAI – Timeline & Clip Utilities

Provides helpers for iterating over timeline clips and reading clip metadata.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from resolve_bridge.connection import get_timeline, get_project


@dataclass
class ClipInfo:
    """Lightweight data container for a timeline clip's metadata."""
    timeline_item: Any          # The raw Resolve TimelineItem object
    name: str = ""
    index: int = 0              # Position in the track
    track: int = 1              # Video track number (1-based)
    start_frame: int = 0
    end_frame: int = 0
    duration_frames: int = 0
    fps: float = 24.0
    media_pool_item: Any = None
    file_path: str = ""
    resolution: str = ""
    codec: str = ""
    color_space: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return self.duration_frames / self.fps if self.fps > 0 else 0


def get_timeline_fps() -> float:
    """Get the frame rate of the current timeline."""
    timeline = get_timeline()
    if timeline is None:
        return 24.0
    setting = timeline.GetSetting("timelineFrameRate")
    try:
        return float(setting) if setting else 24.0
    except (ValueError, TypeError):
        return 24.0


def get_track_count() -> int:
    """Get the number of video tracks in the current timeline."""
    timeline = get_timeline()
    if timeline is None:
        return 0
    return timeline.GetTrackCount("video")


def get_all_clips() -> List[ClipInfo]:
    """
    Get all video clips across all tracks in the current timeline.
    
    Returns:
        List of ClipInfo objects with populated metadata.
    """
    timeline = get_timeline()
    if timeline is None:
        print("[ResolveAI] No active timeline found.")
        return []

    fps = get_timeline_fps()
    track_count = get_track_count()
    clips = []

    for track_idx in range(1, track_count + 1):
        items = timeline.GetItemListInTrack("video", track_idx)
        if not items:
            continue

        for i, item in enumerate(items):
            clip = _build_clip_info(item, index=i, track=track_idx, fps=fps)
            clips.append(clip)

    print(f"[ResolveAI] Found {len(clips)} clips across {track_count} video tracks.")
    return clips


def get_clips_on_track(track: int = 1) -> List[ClipInfo]:
    """Get all clips on a specific video track (1-based)."""
    timeline = get_timeline()
    if timeline is None:
        return []

    fps = get_timeline_fps()
    items = timeline.GetItemListInTrack("video", track)
    if not items:
        return []

    return [_build_clip_info(item, index=i, track=track, fps=fps)
            for i, item in enumerate(items)]


def get_selected_clips() -> List[ClipInfo]:
    """
    Get currently selected clips in the timeline.
    
    Note: The Resolve API may not always support this directly.
    Falls back to returning the current clip on the Color page.
    """
    timeline = get_timeline()
    if timeline is None:
        return []

    fps = get_timeline_fps()

    # Try GetCurrentVideoItem (works on Color page)
    current_item = timeline.GetCurrentVideoItem()
    if current_item is not None:
        return [_build_clip_info(current_item, index=0, track=1, fps=fps)]

    return []


def get_clip_at_playhead() -> Optional[ClipInfo]:
    """Get the clip at the current playhead position."""
    timeline = get_timeline()
    if timeline is None:
        return None

    fps = get_timeline_fps()
    current_item = timeline.GetCurrentVideoItem()
    if current_item is None:
        return None

    return _build_clip_info(current_item, index=0, track=1, fps=fps)


def _build_clip_info(item, index: int, track: int, fps: float) -> ClipInfo:
    """Build a ClipInfo from a Resolve TimelineItem object."""
    clip = ClipInfo(timeline_item=item)
    clip.index = index
    clip.track = track
    clip.fps = fps

    # Basic properties
    try:
        clip.name = item.GetName() or f"Clip_{track}_{index}"
    except Exception:
        clip.name = f"Clip_{track}_{index}"

    try:
        clip.start_frame = item.GetStart()
        clip.end_frame = item.GetEnd()
        clip.duration_frames = clip.end_frame - clip.start_frame
    except Exception:
        pass

    # Media pool item & file path
    try:
        mpi = item.GetMediaPoolItem()
        clip.media_pool_item = mpi
        if mpi:
            clip_props = mpi.GetClipProperty()
            if clip_props:
                clip.file_path = clip_props.get("File Path", "")
                clip.resolution = clip_props.get("Resolution", "")
                clip.codec = clip_props.get("Video Codec", "")
                clip.color_space = clip_props.get("Input Color Space", "")
                clip.properties = clip_props
    except Exception:
        pass

    return clip


def print_timeline_summary():
    """Print a summary of the current timeline for debugging."""
    timeline = get_timeline()
    if timeline is None:
        print("[ResolveAI] No active timeline.")
        return

    project = get_project()
    project_name = project.GetName() if project else "Unknown"
    timeline_name = timeline.GetName() if timeline else "Unknown"

    print(f"\n{'='*60}")
    print(f"  Project: {project_name}")
    print(f"  Timeline: {timeline_name}")
    print(f"  Frame Rate: {get_timeline_fps()} fps")
    print(f"  Video Tracks: {get_track_count()}")
    print(f"{'='*60}")

    clips = get_all_clips()
    for clip in clips:
        print(f"  [{clip.track}:{clip.index}] {clip.name}")
        print(f"           Frames: {clip.start_frame}–{clip.end_frame} "
              f"({clip.duration_seconds:.1f}s)")
        if clip.color_space:
            print(f"           Color Space: {clip.color_space}")
        if clip.file_path:
            print(f"           File: {clip.file_path}")
    print()
