"""
TeamAssigner v2 — hybrid FashionCLIP + HSV torso clustering.

Changes vs. v1:
- Combine CLIP score with HSV mean of the upper-half bbox (jersey region).
- Persist team assignment per track_id with a majority-vote rolling window.
- Remove the buggy reset every 50 frames.
- Configurable via settings.team_assigner_vote_window.
"""
from __future__ import annotations

import collections
import logging

import cv2
import numpy as np
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from configs.settings import settings
from utils import read_stub, save_stub

logger = logging.getLogger(__name__)


class TeamAssigner:
    """
    Assign players to teams (1 or 2) based on jersey appearance.

    Strategy
    --------
    1. Crop the **upper half** of the player bbox (jersey region).
    2. Run FashionCLIP zero-shot to get a soft probability.
    3. Compute mean HSV hue of the jersey crop to break ties.
    4. Persist per track_id with a majority-vote window of length
       `settings.team_assigner_vote_window`.
    """

    def __init__(
        self,
        team_1_class_name: str | None = None,
        team_2_class_name: str | None = None,
        vote_window: int | None = None,
    ) -> None:
        self.team_1_class_name: str = team_1_class_name or settings.team_1_jersey
        self.team_2_class_name: str = team_2_class_name or settings.team_2_jersey
        self.vote_window: int = vote_window or settings.team_assigner_vote_window

        # track_id -> deque of recent team votes
        self._vote_history: dict[int, collections.deque] = {}
        # track_id -> stable team once window is filled
        self._stable_assignment: dict[int, int] = {}

        self._model: CLIPModel | None = None
        self._processor: CLIPProcessor | None = None

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        if self._model is None:
            logger.info("Loading FashionCLIP model…")
            self._model = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")
            self._processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")
            logger.info("FashionCLIP ready")

    def _jersey_crop(self, frame: np.ndarray, bbox: list) -> np.ndarray:
        """Return the upper-half of the player bbox (jersey region)."""
        x1, y1, x2, y2 = (int(v) for v in bbox)
        mid_y = y1 + (y2 - y1) // 2
        return frame[y1:mid_y, x1:x2]

    def _clip_team_probability(self, crop: np.ndarray) -> float:
        """
        Run FashionCLIP and return P(team_1).  Falls back to 0.5 on errors.
        """
        if crop.size == 0:
            return 0.5
        try:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            classes = [self.team_1_class_name, self.team_2_class_name]
            inputs = self._processor(
                text=classes, images=pil_img, return_tensors="pt", padding=True
            )
            outputs = self._model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0]
            return float(probs[0].item())
        except Exception as exc:
            logger.debug("CLIP error: %s", exc)
            return 0.5

    def _hsv_hue_mean(self, crop: np.ndarray) -> float:
        """Return mean hue [0-180] of the jersey crop in HSV space."""
        if crop.size == 0:
            return 90.0
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        return float(np.mean(hsv[:, :, 0]))

    def _classify_player(self, frame: np.ndarray, bbox: list) -> int:
        """
        Return team id (1 or 2) for a single observation.

        Combines CLIP soft probability with HSV hue as a tie-breaker.
        """
        crop = self._jersey_crop(frame, bbox)
        p_team1 = self._clip_team_probability(crop)

        # If CLIP is confident (>0.65) use it directly
        if p_team1 > 0.65:
            return 1
        if p_team1 < 0.35:
            return 2

        # Ambiguous: use HSV hue (low hue = warm/red/yellow → team chosen by
        # which jersey description is "lighter").  Simple heuristic: team 1 if
        # hue < 90 (warm) else team 2.  Works well for common school uniforms.
        hue = self._hsv_hue_mean(crop)
        return 1 if hue < 90 else 2

    def _vote(self, player_id: int, observation: int) -> int:
        """
        Record an observation and return the current majority-vote team.
        """
        if player_id not in self._vote_history:
            self._vote_history[player_id] = collections.deque(maxlen=self.vote_window)

        self._vote_history[player_id].append(observation)
        history = self._vote_history[player_id]

        # Majority vote
        votes = list(history)
        team_1_count = votes.count(1)
        team_2_count = votes.count(2)
        return 1 if team_1_count >= team_2_count else 2

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_player_color(self, frame: np.ndarray, bbox: list) -> str:
        """Legacy helper — returns class name string."""
        crop = self._jersey_crop(frame, bbox)
        p_team1 = self._clip_team_probability(crop)
        return self.team_1_class_name if p_team1 >= 0.5 else self.team_2_class_name

    def get_player_team(
        self, frame: np.ndarray, player_bbox: list, player_id: int
    ) -> int:
        """
        Return team assignment (1 or 2) for a player, using rolling majority vote.
        """
        observation = self._classify_player(frame, player_bbox)
        return self._vote(player_id, observation)

    def get_player_teams_across_frames(
        self,
        video_frames: list,
        player_tracks: list,
        read_from_stub: bool = False,
        stub_path: str | None = None,
    ) -> list[dict[int, int]]:
        """
        Assign teams to all players across all frames with optional stub caching.

        Returns a list of dicts: [{player_id: team_id, …}, …] indexed by frame.
        """
        cached = read_stub(read_from_stub, stub_path)
        if cached is not None and len(cached) == len(video_frames):
            logger.debug("TeamAssigner: loaded from stub %s", stub_path)
            return cached

        self._load_model()
        player_assignment: list[dict[int, int]] = []

        for frame_num, player_track in enumerate(player_tracks):
            frame_assignments: dict[int, int] = {}
            for player_id, track in player_track.items():
                team = self.get_player_team(
                    video_frames[frame_num], track["bbox"], player_id
                )
                frame_assignments[player_id] = team
            player_assignment.append(frame_assignments)

        save_stub(stub_path, player_assignment)
        return player_assignment
