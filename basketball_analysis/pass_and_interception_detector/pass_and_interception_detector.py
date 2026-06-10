from copy import deepcopy


def _ball_center_at(ball_tracks, f):
    if ball_tracks is None or f < 0 or f >= len(ball_tracks):
        return None
    bb = ball_tracks[f].get(1, {}).get("bbox", [])
    if len(bb) < 4:
        return None
    return ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)


def _near_rim(center, rim_box, factor=3.0):
    if center is None or rim_box is None or len(rim_box) < 4:
        return False
    rcx = (rim_box[0] + rim_box[2]) / 2.0
    rcy = (rim_box[1] + rim_box[3]) / 2.0
    rim_w = max(1.0, rim_box[2] - rim_box[0])
    return ((center[0] - rcx) ** 2 + (center[1] - rcy) ** 2) ** 0.5 <= factor * rim_w


class PassAndInterceptionDetector():
    """
    A class that detects passes between teammates and interceptions by opposing teams.

    Optional precision gates (when ball_tracks / rim_sequence are provided):
      - ball must TRAVEL a minimum distance between the two holders (kills phantom
        passes from possession jitter where the ball barely moved),
      - the possession change must happen within a plausible time window,
      - changes NEAR THE RIM are suppressed (likely a shot/rebound, not a pass).
    """
    def __init__(self, min_travel_px: float = 60.0, max_gap_s: float = 2.5):
        self.min_travel_px = min_travel_px
        self.max_gap_s = max_gap_s

    def _valid_transfer(self, ball_tracks, rim_sequence, fps,
                        previous_frame, frame) -> bool:
        """Shared gate for pass/interception: real ball travel, within time window,
        and not at the rim. No-op (always True) when ball_tracks is None."""
        if ball_tracks is None:
            return True
        if fps and (frame - previous_frame) > self.max_gap_s * fps:
            return False
        c_prev = _ball_center_at(ball_tracks, previous_frame)
        c_cur = _ball_center_at(ball_tracks, frame)
        if c_prev is not None and c_cur is not None:
            dist = ((c_cur[0] - c_prev[0]) ** 2 + (c_cur[1] - c_prev[1]) ** 2) ** 0.5
            if dist < self.min_travel_px:
                return False
        if rim_sequence is not None and frame < len(rim_sequence):
            if _near_rim(c_cur, rim_sequence[frame]):
                return False
        return True

    def detect_passes(self, ball_acquisition, player_assignment,
                      ball_tracks=None, rim_sequence=None, fps: float = 30.0):
        """
        Detects successful passes between players of the same team.

        Args:
            ball_acquisition (list): A list indicating which player has possession of the ball in each frame.
            player_assignment (list): A list of dictionaries indicating team assignments for each player
                in the corresponding frame.

        Returns:
            list: A list where each element indicates if a pass occurred in that frame
                (-1: no pass, 1: Team 1 pass, 2: Team 2 pass).
        """
        
        passes = [-1] * len(ball_acquisition)
        prev_holder=-1
        previous_frame=-1

        for frame in range(1, len(ball_acquisition)):
            if ball_acquisition[frame - 1] != -1:
                prev_holder = ball_acquisition[frame - 1]
                previous_frame= frame - 1
            
            current_holder = ball_acquisition[frame]
            
            if prev_holder != -1 and current_holder != -1 and prev_holder != current_holder:
                prev_team = player_assignment[previous_frame].get(prev_holder, -1)
                current_team = player_assignment[frame].get(current_holder, -1)

                if prev_team == current_team and prev_team != -1:
                    if self._valid_transfer(ball_tracks, rim_sequence, fps, previous_frame, frame):
                        passes[frame] = prev_team

        return passes

    def detect_interceptions(self, ball_acquisition, player_assignment,
                             ball_tracks=None, rim_sequence=None, fps: float = 30.0):
        """
        Detects interceptions where the ball possession changes between opposing teams.

        Args:
            ball_acquisition (list): A list indicating which player has possession of the ball in each frame.
            player_assignment (list): A list of dictionaries indicating team assignments for each player
                in the corresponding frame.

        Returns:
            list: A list where each element indicates if an interception occurred in that frame
                (-1: no interception, 1: Team 1 interception, 2: Team 2 interception).
        """
        interceptions = [-1] * len(ball_acquisition)
        prev_holder=-1
        previous_frame=-1
        
        for frame in range(1, len(ball_acquisition)):
            if ball_acquisition[frame - 1] != -1:
                prev_holder = ball_acquisition[frame - 1]
                previous_frame= frame - 1

            current_holder = ball_acquisition[frame]
            
            if prev_holder != -1 and current_holder != -1 and prev_holder != current_holder:
                prev_team = player_assignment[previous_frame].get(prev_holder, -1)
                current_team = player_assignment[frame].get(current_holder, -1)
                
                if prev_team != current_team and prev_team != -1 and current_team != -1:
                    if self._valid_transfer(ball_tracks, rim_sequence, fps, previous_frame, frame):
                        interceptions[frame] = current_team

        return interceptions