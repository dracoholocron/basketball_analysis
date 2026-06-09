import cv2
import numpy as np
import supervision as sv


class CourtKeypointDrawer:
    """
    Draws YOLO-detected court keypoints (red circles) and, when provided,
    manual anchor positions (blue squares) on each frame.

    Parameters
    ----------
    manual_src : np.ndarray | None
        (N, 2) array of pixel coordinates for manually annotated court anchors.
        When set, each anchor is drawn as a blue square on every frame so the
        user can verify the annotations are active.
    """

    def __init__(self, manual_src: np.ndarray | None = None):
        self.keypoint_color = '#ff2c2c'
        self.manual_src = manual_src
        self.vertex_annotator = sv.VertexAnnotator(
            color=sv.Color.from_hex(self.keypoint_color),
            radius=8,
        )
        self.vertex_label_annotator = sv.VertexLabelAnnotator(
            color=sv.Color.from_hex(self.keypoint_color),
            text_color=sv.Color.WHITE,
            text_scale=0.5,
            text_thickness=1,
        )

    def draw(self, frames, court_keypoints):
        output_frames = []
        for index, frame in enumerate(frames):
            output_frames.append(self.draw_frame(frame, index, court_keypoints))
        return output_frames

    def draw_frame(self, frame, frame_num, court_keypoints):
        annotated_frame = frame.copy()

        # Draw YOLO-detected keypoints
        if frame_num < len(court_keypoints):
            keypoints = court_keypoints[frame_num]
            annotated_frame = self.vertex_annotator.annotate(
                scene=annotated_frame, key_points=keypoints
            )
            keypoints_numpy = keypoints.cpu().numpy()
            annotated_frame = self.vertex_label_annotator.annotate(
                scene=annotated_frame, key_points=keypoints_numpy
            )

        # Draw manual anchors as blue squares
        if self.manual_src is not None and len(self.manual_src) > 0:
            for pt in self.manual_src:
                x, y = int(pt[0]), int(pt[1])
                cv2.rectangle(annotated_frame, (x - 6, y - 6), (x + 6, y + 6), (255, 100, 0), 2)

        return annotated_frame
