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
        self._device: str = "cpu"

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        if self._model is None:
            try:
                import torch
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                self._device = "cpu"
            logger.info("Loading FashionCLIP model on %s…", self._device)
            self._model = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip").to(self._device)
            self._processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")
            logger.info("FashionCLIP ready on %s", self._device)

    def _jersey_crop(self, frame: np.ndarray, bbox: list) -> np.ndarray:
        """Return the upper-half of the player bbox (jersey region)."""
        x1, y1, x2, y2 = (int(v) for v in bbox)
        mid_y = y1 + (y2 - y1) // 2
        return frame[y1:mid_y, x1:x2]

    def _clip_team_probability(self, crop: np.ndarray) -> float:
        """Run FashionCLIP on a single crop. Falls back to 0.5 on errors."""
        results = self._clip_team_probabilities_batch([crop])
        return results[0]

    def _clip_team_probabilities_batch(self, crops: list[np.ndarray]) -> list[float]:
        """
        Batch CLIP inference: N crops → N P(team_1) values in one forward pass.

        Skips empty crops (returns 0.5 for them) and processes the rest together,
        which is ~N× faster than calling the model N times individually.
        """
        result = [0.5] * len(crops)
        valid_indices = [i for i, c in enumerate(crops) if c.size > 0]
        if not valid_indices:
            return result
        try:
            import torch
            pil_images = [
                Image.fromarray(cv2.cvtColor(crops[i], cv2.COLOR_BGR2RGB))
                for i in valid_indices
            ]
            classes = [self.team_1_class_name, self.team_2_class_name]
            inputs = self._processor(
                text=classes, images=pil_images, return_tensors="pt", padding=True
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = self._model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[:, 0].tolist()
            for idx, p in zip(valid_indices, probs):
                result[idx] = float(p)
        except Exception as exc:
            logger.debug("CLIP batch error: %s", exc)
        return result

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
        clip_sample_every: int | None = None,
    ) -> list[dict[int, int]]:
        """
        Assign teams to all players across all frames with optional stub caching.

        Parameters
        ----------
        clip_sample_every : int | None
            Run CLIP inference only every Nth frame for each player.
            None uses settings.clip_sample_every (default 30).
            Intermediate frames reuse the last known vote result.

        Returns a list of dicts: [{player_id: team_id, …}, …] indexed by frame.
        """
        cached = read_stub(read_from_stub, stub_path)
        if cached is not None and len(cached) == len(video_frames):
            logger.debug("TeamAssigner: loaded from stub %s", stub_path)
            return cached

        _sample_every = clip_sample_every if clip_sample_every is not None else settings.clip_sample_every
        self._load_model()
        player_assignment: list[dict[int, int]] = []
        total = len(player_tracks)
        last_known: dict[int, int] = {}

        for frame_num, player_track in enumerate(player_tracks):
            frame_assignments: dict[int, int] = {}

            # Log progress every 500 frames
            if frame_num % 500 == 0:
                logger.info(
                    "TeamAssigner: frame %d / %d (%.0f%%)",
                    frame_num, total, frame_num / total * 100,
                )

            # Separate players needing inference from those reusing last vote
            needs_inference: list[int] = []
            for player_id in player_track:
                if frame_num % _sample_every == 0 or player_id not in last_known:
                    needs_inference.append(player_id)

            if needs_inference:
                # Batch all crops for this frame into one forward pass
                crops = [
                    self._jersey_crop(video_frames[frame_num], player_track[pid]["bbox"])
                    for pid in needs_inference
                ]
                probs = self._clip_team_probabilities_batch(crops)
                for player_id, p_team1 in zip(needs_inference, probs):
                    hue = self._hsv_hue_mean(self._jersey_crop(video_frames[frame_num], player_track[player_id]["bbox"])) if 0.35 <= p_team1 <= 0.65 else 90.0
                    obs = 1 if p_team1 > 0.65 else (2 if p_team1 < 0.35 else (1 if hue < 90 else 2))
                    team = self._vote(player_id, obs)
                    last_known[player_id] = team

            for player_id, track in player_track.items():
                frame_assignments[player_id] = last_known.get(player_id, 1)
            player_assignment.append(frame_assignments)

        logger.info("TeamAssigner: done — %d frames processed", total)
        save_stub(stub_path, player_assignment)
        return player_assignment

    def get_player_teams_streaming(
        self,
        video_path: str,
        player_tracks: list[dict],
        chunk_size: int,
        read_from_stub: bool = False,
        stub_path: str | None = None,
        clip_sample_every: int | None = None,
    ) -> list[dict[int, int]]:
        """
        Assign teams across all frames in memory-efficient chunks.

        Re-reads the video chunk by chunk so only `chunk_size` frames are in RAM
        at once. Vote state (_vote_history, _stable_assignment) persists on self
        between chunks automatically, maintaining identity continuity.
        """
        cached = read_stub(read_from_stub, stub_path)
        if cached is not None and len(cached) == len(player_tracks):
            logger.debug("TeamAssigner: loaded from stub %s", stub_path)
            return cached

        _sample_every = clip_sample_every if clip_sample_every is not None else settings.clip_sample_every
        self._load_model()
        player_assignment: list[dict[int, int]] = []
        last_known: dict[int, int] = {}
        total = len(player_tracks)

        from utils.video_utils import iter_video_frames_selective

        # Decode only the frames we actually run CLIP on: every `_sample_every`-th
        # frame PLUS each track's first appearance (so new players are labeled at
        # birth, exactly as before). All other frames are grab()-skipped (no decode)
        # → large speedup with identical results. Precompute the decode set.
        first_appearance: set[int] = set()
        _seen: set[int] = set()
        for _i, _pt in enumerate(player_tracks):
            for _pid in _pt:
                if _pid not in _seen:
                    _seen.add(_pid)
                    first_appearance.add(_i)
        decode_frames = {i for i in range(total) if i % _sample_every == 0} | first_appearance

        def _want(idx: int) -> bool:
            return idx in decode_frames

        for frame_num, frame in iter_video_frames_selective(video_path, _want, max_height=720):
            if frame_num >= total:
                break

            player_track = player_tracks[frame_num]
            frame_assignments: dict[int, int] = {}

            if frame_num % 500 == 0:
                logger.info(
                    "TeamAssigner (streaming): frame %d / %d (%.0f%%)",
                    frame_num, total, frame_num / total * 100,
                )

            # `frame` is None on skipped (non-decoded) frames; only run CLIP when we
            # have pixels (which is exactly the sampled / first-appearance frames).
            if frame is not None:
                needs_inference = [
                    pid for pid in player_track
                    if frame_num % _sample_every == 0 or pid not in last_known
                ]
                if needs_inference:
                    crops = [
                        self._jersey_crop(frame, player_track[pid]["bbox"])
                        for pid in needs_inference
                    ]
                    probs = self._clip_team_probabilities_batch(crops)
                    for pid, p_team1 in zip(needs_inference, probs):
                        hue = self._hsv_hue_mean(self._jersey_crop(frame, player_track[pid]["bbox"])) if 0.35 <= p_team1 <= 0.65 else 90.0
                        obs = 1 if p_team1 > 0.65 else (2 if p_team1 < 0.35 else (1 if hue < 90 else 2))
                        last_known[pid] = self._vote(pid, obs)

            for player_id in player_track:
                frame_assignments[player_id] = last_known.get(player_id, 1)
            player_assignment.append(frame_assignments)

        logger.info(
            "TeamAssigner (streaming): done — %d frames (%d decoded, %d skipped)",
            total, len(decode_frames), total - len(decode_frames),
        )
        save_stub(stub_path, player_assignment)
        return player_assignment
