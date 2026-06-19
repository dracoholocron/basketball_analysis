import cv2


class BallTracksDrawer:
    """Draws the ball box, color-coded by which model produced it, so YOLO vs SAM2 vs
    SAHI vs interpolation is visible frame by frame."""

    COLOR = (0, 165, 255)   # default orange (BGR)

    # Per-source colors (BGR) + short label.
    SOURCE_STYLE = {
        "yolo":   ((0, 255, 0),     "YOLO"),    # green  — automatic detector
        "sam2":   ((0, 165, 255),   "SAM2"),    # orange — propagated from annotation
        "sahi":   ((255, 200, 0),   "SAHI"),    # cyan   — tiled refill
        "kalman": ((180, 180, 180), "Kalman"),  # gray   — predicted
        "interp": ((130, 130, 130), "interp"),  # gray   — interpolated
    }

    def draw(self, video_frames, tracks, sources=None):
        return [
            self.draw_frame(frame, i, tracks, sources)
            for i, frame in enumerate(video_frames)
        ]

    # Sources considered "predicted" (no real detection this frame) — skipped from the
    # drawn video by default so the ball only appears where it was actually seen.
    PREDICTED_SOURCES = ("kalman", "interp")

    def draw_frame(self, frame, frame_num, tracks, sources=None, draw_predicted=False):
        frame = frame.copy()
        ball_dict = tracks[frame_num] if frame_num < len(tracks) else {}
        src = ""
        if sources is not None and frame_num < len(sources):
            src = sources[frame_num] or ""
        # Don't draw phantom balls (Kalman/interp extrapolation) unless explicitly asked.
        if src in self.PREDICTED_SOURCES and not draw_predicted:
            return frame
        color, tag = self.SOURCE_STYLE.get(src, (self.COLOR, "Ball"))
        for _, ball in ball_dict.items():
            bbox = ball.get("bbox")
            if not bbox:
                continue
            x1, y1, x2, y2 = (int(v) for v in bbox)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame, tag, (x1, max(y1 - 6, 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,
            )
        return frame
