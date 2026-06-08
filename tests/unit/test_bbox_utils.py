"""Unit tests for bbox_utils."""
import math
import pytest


def test_get_center_of_bbox():
    from utils.bbox_utils import get_center_of_bbox
    assert get_center_of_bbox([0, 0, 10, 10]) == (5, 5)
    assert get_center_of_bbox([2, 4, 12, 14]) == (7, 9)


def test_get_bbox_width():
    from utils.bbox_utils import get_bbox_width
    assert get_bbox_width([0, 0, 10, 10]) == 10
    assert get_bbox_width([5, 0, 15, 10]) == 10


def test_measure_distance():
    from utils.bbox_utils import measure_distance
    assert math.isclose(measure_distance((0, 0), (3, 4)), 5.0)
    assert math.isclose(measure_distance((0, 0), (0, 0)), 0.0)


def test_get_foot_position():
    from utils.bbox_utils import get_foot_position
    # foot = bottom center = (mid_x, y2)
    x, y = get_foot_position([0, 0, 10, 20])
    assert x == 5
    assert y == 20


def test_measure_xy_distance():
    from utils.bbox_utils import measure_xy_distance
    # measure_xy_distance(p1, p2) returns (p1.x - p2.x, p1.y - p2.y)
    dx, dy = measure_xy_distance((3, 4), (6, 8))
    assert dx == -3  # 3 - 6 = -3
    assert dy == -4  # 4 - 8 = -4

    # Reversed order
    dx2, dy2 = measure_xy_distance((6, 8), (3, 4))
    assert dx2 == 3
    assert dy2 == 4
