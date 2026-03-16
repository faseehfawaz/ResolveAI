"""
ResolveAI – Frame Grabber

Extracts representative frames from video clips for color analysis.
Uses OpenCV to read frames directly from source media files.
"""

import os
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None
    print("[ResolveAI] WARNING: OpenCV not installed. Run: pip install opencv-python")

from config import FRAMES_PER_CLIP


def grab_frames_from_file(file_path: str, num_frames: int = None) -> list:
    """
    Extract evenly-spaced frames from a video file.
    
    Args:
        file_path: Absolute path to the video file.
        num_frames: Number of frames to extract (default: FRAMES_PER_CLIP).
    
    Returns:
        List of numpy arrays (BGR images) – one per sampled frame.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV is required. Install with: pip install opencv-python")

    if not os.path.isfile(file_path):
        print(f"[ResolveAI] File not found: {file_path}")
        return []

    if num_frames is None:
        num_frames = FRAMES_PER_CLIP

    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        print(f"[ResolveAI] Could not open video: {file_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        print(f"[ResolveAI] Could not determine frame count: {file_path}")
        cap.release()
        return []

    # Calculate evenly-spaced frame indices (skip first/last 5%)
    margin = max(1, int(total_frames * 0.05))
    usable_start = margin
    usable_end = total_frames - margin

    if usable_end <= usable_start:
        # Very short clip – just grab the middle frame
        indices = [total_frames // 2]
    elif num_frames == 1:
        indices = [(usable_start + usable_end) // 2]
    else:
        step = (usable_end - usable_start) / (num_frames - 1)
        indices = [int(usable_start + i * step) for i in range(num_frames)]

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)

    cap.release()
    print(f"[ResolveAI] Grabbed {len(frames)} frames from "
          f"'{os.path.basename(file_path)}' ({total_frames} total frames)")
    return frames


def grab_frames_from_clip(clip_info, num_frames: int = None) -> list:
    """
    Extract representative frames from a ClipInfo object.
    
    Uses the clip's file_path if available, otherwise returns empty.
    
    Args:
        clip_info: A ClipInfo object from resolve_bridge.timeline.
        num_frames: Number of frames to extract.
    
    Returns:
        List of numpy arrays (BGR images).
    """
    if not clip_info.file_path:
        print(f"[ResolveAI] No file path for clip '{clip_info.name}' – "
              f"cannot grab frames.")
        return []

    return grab_frames_from_file(clip_info.file_path, num_frames)


def frames_to_rgb(frames: list) -> list:
    """Convert a list of BGR frames (from OpenCV) to RGB."""
    if cv2 is None:
        return frames
    return [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames]


def resize_for_analysis(frames: list, max_width: int = 640) -> list:
    """
    Resize frames to a max width for faster analysis.
    
    Color histograms and statistics don't need full resolution.
    Downscaling significantly speeds up processing.
    """
    if cv2 is None:
        return frames

    resized = []
    for frame in frames:
        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / w
            new_w = max_width
            new_h = int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        resized.append(frame)
    return resized


def create_composite_frame(frames: list) -> np.ndarray:
    """
    Create a single composite frame by averaging all sample frames.
    
    This gives us a representative "average" of the entire clip,
    smoothing out any outlier frames (e.g., flash, black frames).
    
    Args:
        frames: List of numpy arrays, all same dimensions.
    
    Returns:
        A single averaged frame as numpy array.
    """
    if not frames:
        raise ValueError("No frames to composite")

    # Ensure all frames are the same size (resize to smallest)
    min_h = min(f.shape[0] for f in frames)
    min_w = min(f.shape[1] for f in frames)
    
    if cv2 is not None:
        resized = [cv2.resize(f, (min_w, min_h)) for f in frames]
    else:
        resized = frames

    # Average all frames (float to avoid overflow)
    accumulator = np.zeros_like(resized[0], dtype=np.float64)
    for frame in resized:
        accumulator += frame.astype(np.float64)
    
    composite = (accumulator / len(resized)).astype(np.uint8)
    return composite
