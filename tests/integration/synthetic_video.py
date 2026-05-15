"""
Helper: create a minimal synthetic video file for integration tests.

The video has n_frames of pure-color frames with a moving white circle
(simulating a ball) and coloured rectangles (players).  No YOLO models
are used — we bypass detection by providing pre-built stubs.
"""
from __future__ import annotations

import os
import tempfile

import cv2
import numpy as np


def make_synthetic_video(
    n_frames: int = 30,
    width: int = 640,
    height: int = 480,
    fps: float = 24.0,
    output_path: str | None = None,
) -> str:
    """
    Generate a synthetic AVI video and return the file path.

    If `output_path` is None a temp file is created.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".avi")
        os.close(fd)

    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for i in range(n_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Green court background
        frame[:] = (34, 100, 34)

        # Player 1 (white jersey, team 1) — moves right
        p1_x = 100 + i * 5
        cv2.rectangle(frame, (p1_x, 200), (p1_x + 40, 280), (220, 220, 220), -1)

        # Player 2 (dark blue jersey, team 2) — static
        cv2.rectangle(frame, (400, 200), (440, 280), (100, 50, 30), -1)

        # Ball (white circle) — near player 1
        ball_x = p1_x + 20
        cv2.circle(frame, (ball_x, 250), 10, (255, 255, 255), -1)

        out.write(frame)

    out.release()
    return output_path


def make_synthetic_stubs(
    n_frames: int = 30,
    width: int = 640,
    fps: float = 24.0,
    stub_dir: str | None = None,
) -> str:
    """
    Pre-build stubs (player/ball/keypoint tracks) for the synthetic video.

    Returns the stub directory path so pipeline can be called with use_stubs=True.
    """
    import pickle

    if stub_dir is None:
        stub_dir = tempfile.mkdtemp()

    os.makedirs(stub_dir, exist_ok=True)

    # Player tracks: 2 players moving right (player 1) and static (player 2)
    player_tracks = []
    for i in range(n_frames):
        p1_x = 100 + i * 5
        player_tracks.append({
            1: {"bbox": [p1_x, 200, p1_x + 40, 280]},
            2: {"bbox": [400, 200, 440, 280]},
        })
    with open(os.path.join(stub_dir, "player_track_stubs.pkl"), "wb") as f:
        pickle.dump(player_tracks, f)

    # Ball tracks near player 1
    ball_tracks = []
    for i in range(n_frames):
        ball_x = 120 + i * 5
        ball_tracks.append({1: {"bbox": [ball_x - 10, 240, ball_x + 10, 260]}})
    with open(os.path.join(stub_dir, "ball_track_stubs.pkl"), "wb") as f:
        pickle.dump(ball_tracks, f)

    # Court keypoints stub: all zeros (homography will skip these frames)
    try:
        import torch
        # Create a mock supervisione-like keypoints object using a simple class
        class _MockKP:
            def __init__(self):
                self.xy = torch.zeros(1, 18, 2)
                self.xyn = torch.zeros(1, 18, 2)
        kp_list = [_MockKP() for _ in range(n_frames)]
    except ImportError:
        kp_list = []

    with open(os.path.join(stub_dir, "court_key_points_stub.pkl"), "wb") as f:
        pickle.dump(kp_list, f)

    # Player assignment stub: player 1 → team 1, player 2 → team 2
    assignment = [{1: 1, 2: 2}] * n_frames
    with open(os.path.join(stub_dir, "player_assignment_stub.pkl"), "wb") as f:
        pickle.dump(assignment, f)

    return stub_dir
