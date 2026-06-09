import cv2


class BallTracksDrawer:
    """Draws a visible bounding box + 'Ball' label on each detected ball."""

    COLOR = (0, 165, 255)   # orange (BGR)

    def draw(self, video_frames, tracks):
        output_video_frames = []
        for frame_num, frame in enumerate(video_frames):
            frame = self.draw_frame(frame, frame_num, tracks)
            output_video_frames.append(frame)
        return output_video_frames

    def draw_frame(self, frame, frame_num, tracks):
        frame = frame.copy()
        ball_dict = tracks[frame_num] if frame_num < len(tracks) else {}
        for _, ball in ball_dict.items():
            bbox = ball.get("bbox")
            if not bbox:
                continue
            x1, y1, x2, y2 = (int(v) for v in bbox)
            cv2.rectangle(frame, (x1, y1), (x2, y2), self.COLOR, 2)
            cv2.putText(
                frame, "Ball", (x1, max(y1 - 6, 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.COLOR, 2,
            )
        return frame
