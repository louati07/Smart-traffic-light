"""Unit tests for the Sliding Window Debounce Filter."""

from vision.debounce import DebounceFilter


def test_flicker_does_not_confirm():
    """Sporadic flickering detections (e.g. 2 frames out of 8) should NOT confirm."""
    db = DebounceFilter(window_w=8, confirm_k=5, min_confidence=0.55)

    # 2 frames of ambulance
    res1 = db.update("N", "ambulance", 0.8, 0.02, frame_id=1, timestamp_s=0.0)
    assert not res1.confirmed
    res2 = db.update("N", "ambulance", 0.85, 0.02, frame_id=2, timestamp_s=0.1)
    assert not res2.confirmed

    # 4 frames of background vehicle/none
    for f in range(3, 7):
        res = db.update("N", "vehicle", 0.9, 0.05, frame_id=f, timestamp_s=f * 0.1)
        assert not res.confirmed


def test_steady_detection_confirms():
    """Consistent detections reaching K=5 frames should confirm emergency vehicle."""
    db = DebounceFilter(window_w=8, confirm_k=5, min_confidence=0.55)

    # First 4 frames: not confirmed yet
    for f in range(1, 5):
        res = db.update("N", "ambulance", 0.75, 0.02, frame_id=f, timestamp_s=f * 0.1)
        assert not res.confirmed

    # 5th frame: reaches K=5 threshold -> CONFIRMED
    res5 = db.update("N", "ambulance", 0.80, 0.02, frame_id=5, timestamp_s=0.5)
    assert res5.confirmed
    assert res5.dominant_class == "ambulance"


def test_low_confidence_and_small_bbox_rejected():
    """Detections with confidence < 0.55 or bbox area < 0.005 are gated out."""
    db = DebounceFilter(window_w=8, confirm_k=5, min_confidence=0.55, min_bbox_area_ratio=0.005)

    # 6 frames of low confidence (0.4)
    for f in range(1, 7):
        res = db.update("N", "ambulance", 0.40, 0.02, frame_id=f, timestamp_s=f * 0.1)
        assert not res.confirmed

    # 6 frames of tiny bbox (0.001)
    for f in range(7, 13):
        res = db.update("N", "ambulance", 0.90, 0.001, frame_id=f, timestamp_s=f * 0.1)
        assert not res.confirmed


def test_release_after_timeout():
    """Once confirmed, ceasing detections for release_after_s releases the priority hold."""
    db = DebounceFilter(window_w=8, confirm_k=3, release_after_s=2.0)

    # 3 frames -> Confirmed
    for f in range(1, 4):
        db.update("S", "fire_truck", 0.9, 0.03, frame_id=f, timestamp_s=1.0 + f * 0.1)

    assert db.is_confirmed["S"] is True

    # 1.0s later with empty frames -> still within hold period
    res_hold = db.update("S", "none", 0.0, 0.0, frame_id=5, timestamp_s=2.3)
    assert res_hold.confirmed

    # 3.5s later (> 2.0s since last seen at 1.3s) -> Released
    res_rel = db.update("S", "none", 0.0, 0.0, frame_id=6, timestamp_s=4.0)
    assert not res_rel.confirmed
    assert db.is_confirmed["S"] is False
