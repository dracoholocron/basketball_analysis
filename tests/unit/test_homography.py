"""Unit tests for Homography — transform a known square to a known rectangle."""
import math
import numpy as np
import pytest


def test_unit_square_to_rectangle():
    """Map a [0,1]² unit square to a [0,100]×[0,50] rectangle."""
    from tactical_view_converter.homography import Homography

    src = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    dst = np.array([[0, 0], [100, 0], [100, 50], [0, 50]], dtype=np.float32)
    h = Homography(src, dst)

    # Center of unit square → center of rectangle
    result = h.transform_points(np.array([[0.5, 0.5]], dtype=np.float32))
    assert math.isclose(result[0][0], 50.0, abs_tol=1e-3)
    assert math.isclose(result[0][1], 25.0, abs_tol=1e-3)

    # All four corners round-trip
    back = h.transform_points(src)
    for i in range(4):
        assert math.isclose(back[i][0], dst[i][0], abs_tol=0.5)
        assert math.isclose(back[i][1], dst[i][1], abs_tol=0.5)


def test_identity_transform():
    """If src == dst the transform should be (near) identity."""
    from tactical_view_converter.homography import Homography

    pts = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=np.float32)
    h = Homography(pts, pts)
    result = h.transform_points(np.array([[5, 5]], dtype=np.float32))
    assert math.isclose(result[0][0], 5.0, abs_tol=0.5)
    assert math.isclose(result[0][1], 5.0, abs_tol=0.5)
