import cv2
class FrameNumberDrawer:
    def __init__(self):
        pass

    def draw(self, frames):
        output_frames = []
        for i in range(len(frames)):
            output_frames.append(self.draw_frame(frames[i], i))
        return output_frames

    def draw_frame(self, frame, frame_num):
        frame = frame.copy()
        cv2.putText(frame, str(frame_num), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        return frame