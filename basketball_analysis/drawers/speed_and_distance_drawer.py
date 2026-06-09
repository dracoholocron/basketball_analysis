import cv2

class SpeedAndDistanceDrawer():
    def __init__(self):
        pass

    def draw(self, video_frames, player_tracks, player_distances_per_frame, player_speed_per_frame):
        output_video_frames = []
        total_distances = {}
        for frame_num, frame in enumerate(video_frames):
            output_frame = self.draw_frame(
                frame, frame_num,
                player_tracks, player_distances_per_frame, player_speed_per_frame,
                total_distances,
            )
            output_video_frames.append(output_frame)
        return output_video_frames

    def draw_frame(self, frame, frame_num, player_tracks, player_distances_per_frame,
                   player_speed_per_frame, total_distances: dict):
        """Draw speed and distance overlays for a single frame.

        ``total_distances`` is mutated in-place to accumulate distances across frames;
        pass the same dict on every call to get cumulative values.
        """
        output_frame = frame.copy()
        player_distance = player_distances_per_frame[frame_num] if frame_num < len(player_distances_per_frame) else {}
        player_speed    = player_speed_per_frame[frame_num]     if frame_num < len(player_speed_per_frame)    else {}
        tracks_frame    = player_tracks[frame_num]              if frame_num < len(player_tracks)             else {}

        for player_id, distance in player_distance.items():
            if player_id not in total_distances:
                total_distances[player_id] = 0
            total_distances[player_id] += distance

        for player_id, bbox in tracks_frame.items():
            x1, y1, x2, y2 = bbox['bbox']
            position = [int((x1 + x2) / 2), int(y2)]
            position[1] += 40
            speed = player_speed.get(player_id, None)
            dist  = total_distances.get(player_id, None)
            if speed is not None:
                cv2.putText(output_frame, f"{speed:.2f} km/h", position,
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
            if dist is not None:
                cv2.putText(output_frame, f"{dist:.2f} m", (position[0], position[1] + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        return output_frame