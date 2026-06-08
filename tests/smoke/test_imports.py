"""
Smoke tests: verify all packages can be imported without sys.path hacks.

Run with: pytest tests/smoke/test_imports.py -v
"""
import pytest


def test_import_bbox_utils():
    from utils.bbox_utils import (
        get_center_of_bbox,
        get_bbox_width,
        measure_distance,
        measure_xy_distance,
        get_foot_position,
    )
    assert callable(get_center_of_bbox)


def test_import_stubs_utils():
    from utils.stubs_utils import save_stub, read_stub
    assert callable(save_stub)
    assert callable(read_stub)


def test_import_video_utils():
    from utils.video_utils import read_video, save_video, iter_video_frames, get_video_properties
    assert callable(iter_video_frames)


def test_import_court_mode_detector():
    from utils.court_mode_detector import CourtModeDetector
    assert CourtModeDetector is not None


def test_import_ball_aquisition():
    from ball_aquisition.ball_aquisition_detector import BallAquisitionDetector
    det = BallAquisitionDetector()
    assert det.min_frames > 0


def test_import_pass_interception():
    from pass_and_interception_detector.pass_and_interception_detector import (
        PassAndInterceptionDetector,
    )
    det = PassAndInterceptionDetector()
    assert det is not None


def test_import_speed_distance():
    from speed_and_distance_calculator.speed_and_distance_calculator import (
        SpeedAndDistanceCalculator,
    )
    calc = SpeedAndDistanceCalculator(300, 161, 28.0, 15.0)
    assert calc.fps > 0


def test_import_configs():
    from configs.settings import settings, CourtProfile, CourtLevel
    profile = CourtProfile.from_level(CourtLevel.PRIMARIA)
    assert profile.width_m == 24.0


def test_settings_new_fields():
    """Smoke: new settings fields added in the plan must exist and have sane defaults."""
    from configs.settings import settings

    assert hasattr(settings, "yolo_batch_size"), "yolo_batch_size must be in settings"
    assert hasattr(settings, "clip_batch_size"), "clip_batch_size must be in settings"
    assert hasattr(settings, "speed_max_kmh"), "speed_max_kmh must be in settings"
    assert settings.yolo_batch_size > 0
    assert settings.clip_batch_size > 0
    assert settings.speed_max_kmh > 0
    assert settings.speed_window_frames == 25, (
        f"Expected speed_window_frames=25, got {settings.speed_window_frames}"
    )
    assert settings.min_possession_frames == 6, (
        f"Expected min_possession_frames=6, got {settings.min_possession_frames}"
    )


def test_speed_clamp_import():
    """Smoke: SpeedAndDistanceCalculator must import and accept max_speed_kmh kwarg."""
    from speed_and_distance_calculator.speed_and_distance_calculator import (
        SpeedAndDistanceCalculator,
    )
    calc = SpeedAndDistanceCalculator(
        300, 161, 28.0, 15.0, max_speed_kmh=40.0
    )
    assert calc.max_speed_kmh == 40.0


def test_ball_aquisition_frame_width():
    """Smoke: BallAquisitionDetector must accept frame_width and scale threshold."""
    from ball_aquisition.ball_aquisition_detector import BallAquisitionDetector

    det = BallAquisitionDetector(possession_threshold=50.0, frame_width=1280)
    assert det.possession_threshold == 50.0  # 1280/1280 * 50 = 50


def test_import_homography():
    import numpy as np
    from tactical_view_converter.homography import Homography
    src = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    dst = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.float32)
    h = Homography(src, dst)
    result = h.transform_points(np.array([[0.5, 0.5]]))
    assert result.shape == (1, 2)


def test_api_health(api_base_url):
    """Skip unless API_URL env var is set (requires running API service)."""
    pytest.importorskip("httpx")
    import httpx
    r = httpx.get(f"{api_base_url}/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: requires live services (API, DB, Redis, MinIO)")


@pytest.fixture(scope="session")
def api_base_url():
    url = os.environ.get("API_BASE_URL", "")
    if not url:
        pytest.skip("API_BASE_URL not set — skipping live service test")
    return url


import os
