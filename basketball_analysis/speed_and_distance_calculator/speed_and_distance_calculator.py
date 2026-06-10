from utils import measure_distance
from configs.settings import settings


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

    def calculate_distance(self, tactical_player_positions: list) -> list:
        previous_players_position: dict = {}
        smoothed: dict = {}  # per-player EMA-smoothed position
        output_distances: list = []
        a = self.smooth_alpha

        for frame_number, tactical_player_position_frame in enumerate(
            tactical_player_positions
        ):
            output_distances.append({})
            for player_id, raw_pos in tactical_player_position_frame.items():
                # EMA-smooth the tactical position to remove homography jitter.
                if player_id in smoothed and a < 1.0:
                    sx = a * raw_pos[0] + (1 - a) * smoothed[player_id][0]
                    sy = a * raw_pos[1] + (1 - a) * smoothed[player_id][1]
                    cur = [sx, sy]
                else:
                    cur = [raw_pos[0], raw_pos[1]]
                smoothed[player_id] = cur

                if player_id in previous_players_position:
                    meter_distance = self._calculate_meter_distance(
                        previous_players_position[player_id], cur
                    )
                    output_distances[frame_number][player_id] = meter_distance
                previous_players_position[player_id] = cur

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
