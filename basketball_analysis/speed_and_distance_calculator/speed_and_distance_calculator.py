from utils import measure_distance
from configs.settings import settings

try:
    from scipy.signal import savgol_filter
    _HAS_SAVGOL = True
except Exception:  # pragma: no cover - scipy should be present in the engine image
    _HAS_SAVGOL = False


class SpeedAndDistanceCalculator:
    def __init__(
        self,
        width_in_pixels: float,
        height_in_pixels: float,
        width_in_meters: float,
        height_in_meters: float,
        fps: float | None = None,
        calibration_factor: float | None = None,
        window_size: int | None = None,
        max_speed_kmh: float | None = None,
    ):
        self.width_in_pixels = width_in_pixels
        self.height_in_pixels = height_in_pixels
        self.width_in_meters = width_in_meters
        self.height_in_meters = height_in_meters
        self.fps = fps if fps is not None else settings.fps
        self.calibration_factor = (
            calibration_factor if calibration_factor is not None else 1.0
        )
        self.window_size = (
            window_size if window_size is not None else settings.speed_window_frames
        )
        self.max_speed_kmh = (
            max_speed_kmh if max_speed_kmh is not None else settings.speed_max_kmh
        )
        self.deadband_m = getattr(settings, "speed_deadband_m", 0.08)
        self.smooth_alpha = getattr(settings, "speed_smooth_alpha", 0.4)
        self.savgol_window = int(getattr(settings, "speed_savgol_window", 9))
        self.instantaneous_max_kmh = float(getattr(settings, "speed_instantaneous_max_kmh", 32.0))

    def _smooth_track(self, frames: list[int], xs: list[float], ys: list[float]):
        """Savitzky-Golay smoothing of one player's tactical trajectory (x,y over its
        sampled frames). Falls back to raw when scipy is missing or the track is too
        short for the window. Removes high-frequency homography jitter with little lag."""
        n = len(frames)
        w = self.savgol_window
        if not _HAS_SAVGOL or w < 3 or n < w:
            return xs, ys
        if w % 2 == 0:
            w += 1
        if w > n:
            w = n if n % 2 == 1 else n - 1
        if w < 3:
            return xs, ys
        poly = min(2, w - 1)
        sx = savgol_filter(xs, w, poly)
        sy = savgol_filter(ys, w, poly)
        return list(sx), list(sy)

    def calculate_distance(self, tactical_player_positions: list) -> list:
        n_frames = len(tactical_player_positions)
        output_distances: list = [dict() for _ in range(n_frames)]
        if n_frames == 0:
            return output_distances

        # 1) Collect each player's tactical-pixel trajectory over the frames it appears in.
        series: dict = {}  # player_id -> (frames[], xs[], ys[])
        for f, frame_pos in enumerate(tactical_player_positions):
            for pid, pos in frame_pos.items():
                fr, xs, ys = series.setdefault(pid, ([], [], []))
                fr.append(f); xs.append(float(pos[0])); ys.append(float(pos[1]))

        # 2) Smooth each trajectory (Savitzky-Golay) → per-player {frame: (x,y)}.
        smoothed: dict = {}
        for pid, (fr, xs, ys) in series.items():
            sx, sy = self._smooth_track(fr, xs, ys)
            smoothed[pid] = {fr[i]: (sx[i], sy[i]) for i in range(len(fr))}

        # 3) Per-frame meter distance from the previous present frame, with a kinematic
        #    gate that drops physically implausible jumps (jitter / tracking ID switches).
        max_inst_m_per_frame = (self.instantaneous_max_kmh / 3.6) / max(self.fps, 1e-6)
        previous_players_position: dict = {}  # pid -> (frame, x_m, y_m)
        for f in range(n_frames):
            for pid in tactical_player_positions[f].keys():
                pt = smoothed.get(pid, {}).get(f)
                if pt is None:
                    continue
                cur_m_x = pt[0] * self.width_in_meters / self.width_in_pixels
                cur_m_y = pt[1] * self.height_in_meters / self.height_in_pixels
                if pid in previous_players_position:
                    pf, pmx, pmy = previous_players_position[pid]
                    dist = measure_distance((cur_m_x, cur_m_y), (pmx, pmy)) * self.calibration_factor
                    gap = max(1, f - pf)
                    if (dist / gap) > max_inst_m_per_frame:
                        dist = 0.0   # kinematic outlier → drop this step
                    elif dist < self.deadband_m:
                        dist = 0.0   # jitter deadband
                    output_distances[f][pid] = dist
                previous_players_position[pid] = (f, cur_m_x, cur_m_y)

        return output_distances

    def _calculate_meter_distance(
        self,
        previous_pixel_position: tuple,
        current_pixel_position: tuple,
    ) -> float:
        prev_x, prev_y = previous_pixel_position
        curr_x, curr_y = current_pixel_position

        prev_m_x = prev_x * self.width_in_meters / self.width_in_pixels
        prev_m_y = prev_y * self.height_in_meters / self.height_in_pixels
        curr_m_x = curr_x * self.width_in_meters / self.width_in_pixels
        curr_m_y = curr_y * self.height_in_meters / self.height_in_pixels

        dist = measure_distance((curr_m_x, curr_m_y), (prev_m_x, prev_m_y)) * self.calibration_factor
        # Deadband: sub-threshold motion is jitter, not real displacement.
        if dist < self.deadband_m:
            return 0.0
        return dist

    # Keep old name for backwards compatibility
    def calculate_meter_distance(self, previous_pixel_position, current_pixel_position):
        return self._calculate_meter_distance(previous_pixel_position, current_pixel_position)

    def calculate_speed(
        self,
        distances: list,
        fps: float | None = None,
    ) -> list:
        """
        Calculate player speeds (km/h) using a rolling window over `window_size` frames.

        Args:
            distances: Per-frame dicts mapping player_id -> meter distance since previous frame.
            fps: Override video FPS (defaults to self.fps).

        Returns:
            Per-frame dicts mapping player_id -> speed in km/h.
        """
        effective_fps = fps if fps is not None else self.fps
        speeds: list = []
        window = self.window_size

        for frame_idx in range(len(distances)):
            speeds.append({})
            for player_id in distances[frame_idx].keys():
                start_frame = max(0, frame_idx - (window * 3) + 1)
                total_distance = 0.0
                frames_present = 0
                last_seen = None

                for i in range(start_frame, frame_idx + 1):
                    if player_id in distances[i]:
                        if last_seen is not None:
                            total_distance += distances[i][player_id]
                            frames_present += 1
                        last_seen = i

                if frames_present >= window:
                    time_in_seconds = frames_present / effective_fps
                    time_in_hours = time_in_seconds / 3600
                    if time_in_hours > 0:
                        speed_kmh = (total_distance / 1000) / time_in_hours
                        speed_kmh = min(speed_kmh, self.max_speed_kmh)
                        speeds[frame_idx][player_id] = speed_kmh
                    else:
                        speeds[frame_idx][player_id] = 0.0
                else:
                    speeds[frame_idx][player_id] = 0.0

        return speeds
