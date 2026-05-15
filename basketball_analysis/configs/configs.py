"""
Legacy constants re-exported from settings for backwards compatibility.
New code should import from configs.settings instead.
"""
from .settings import settings

STUBS_DEFAULT_PATH = settings.stubs_default_path
PLAYER_DETECTOR_PATH = settings.player_detector_path
BALL_DETECTOR_PATH = settings.ball_detector_path
COURT_KEYPOINT_DETECTOR_PATH = settings.court_keypoint_detector_path
OUTPUT_VIDEO_PATH = settings.output_video_path
