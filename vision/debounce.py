"""Sliding Window Debounce Filter for AI Emergency Vehicle Detections.

Contract (PLAN.md Section 8 P4 & config.yaml):
- Window W = 8 inferred frames
- Confirm threshold K = 5 frames
- Confidence threshold >= 0.55
- Bounding box area ratio >= 0.005
- Confirmed state released when no emergency class is observed for release_after_s (default 3.0s).
"""

import time
from collections import deque
from dataclasses import dataclass

EMERGENCY_CLASSES = {"ambulance", "fire_truck", "police_car"}


@dataclass
class RawFrameDetection:
    frame_id: int
    approach: str
    vehicle_class: str
    confidence: float
    bbox_area_ratio: float
    timestamp_s: float


@dataclass
class DebounceResult:
    confirmed: bool
    dominant_class: str | None
    confidence: float
    reason: str


class DebounceFilter:
    """Sliding-window confirmation filter per approach."""

    def __init__(
        self,
        window_w: int = 8,
        confirm_k: int = 5,
        min_confidence: float = 0.55,
        min_bbox_area_ratio: float = 0.005,
        release_after_s: float = 3.0,
    ) -> None:
        self.window_w = window_w
        self.confirm_k = confirm_k
        self.min_confidence = min_confidence
        self.min_bbox_area_ratio = min_bbox_area_ratio
        self.release_after_s = release_after_s

        # History per approach: approach -> deque of RawFrameDetection
        self.history: dict[str, deque[RawFrameDetection]] = {}
        # Confirmed state tracking per approach: approach -> bool
        self.is_confirmed: dict[str, bool] = {}
        # Last confirmed detection timestamp per approach: approach -> timestamp_s
        self.last_seen_s: dict[str, float] = {}

    def update(
        self,
        approach: str,
        vehicle_class: str,
        confidence: float,
        bbox_area_ratio: float,
        frame_id: int,
        timestamp_s: float | None = None,
    ) -> DebounceResult:
        now = timestamp_s if timestamp_s is not None else time.time()
        app = approach.upper().strip()

        if app not in self.history:
            self.history[app] = deque(maxlen=self.window_w)
            self.is_confirmed[app] = False
            self.last_seen_s[app] = 0.0

        # Check if detection passes spatial and confidence gates
        is_valid_emergency = (
            vehicle_class.lower() in EMERGENCY_CLASSES
            and confidence >= self.min_confidence
            and bbox_area_ratio >= self.min_bbox_area_ratio
        )

        det = RawFrameDetection(
            frame_id=frame_id,
            approach=app,
            vehicle_class=vehicle_class.lower() if is_valid_emergency else "none",
            confidence=confidence if is_valid_emergency else 0.0,
            bbox_area_ratio=bbox_area_ratio if is_valid_emergency else 0.0,
            timestamp_s=now,
        )
        self.history[app].append(det)

        if is_valid_emergency:
            self.last_seen_s[app] = now

        # Check release condition first if previously confirmed
        if self.is_confirmed[app] and (now - self.last_seen_s[app]) >= self.release_after_s:
            self.is_confirmed[app] = False
            self.history[app].clear()
            return DebounceResult(
                confirmed=False,
                dominant_class=None,
                confidence=0.0,
                reason=f"Released: no emergency detection for {self.release_after_s}s",
            )

        # Count emergency frames in the window
        class_counts: dict[str, int] = {}
        total_emergency_frames = 0
        total_conf = 0.0

        for item in self.history[app]:
            if item.vehicle_class in EMERGENCY_CLASSES:
                total_emergency_frames += 1
                class_counts[item.vehicle_class] = class_counts.get(item.vehicle_class, 0) + 1
                total_conf += item.confidence

        # Confirmation condition: K out of W frames
        if total_emergency_frames >= self.confirm_k:
            self.is_confirmed[app] = True
            dominant_cls = max(class_counts.items(), key=lambda x: x[1])[0]
            avg_conf = total_conf / total_emergency_frames
            return DebounceResult(
                confirmed=True,
                dominant_class=dominant_cls,
                confidence=round(avg_conf, 3),
                reason=f"Confirmed: {total_emergency_frames}/{self.window_w} frames detected",
            )

        # Still within active hold window
        if self.is_confirmed[app]:
            return DebounceResult(
                confirmed=True,
                dominant_class=vehicle_class if is_valid_emergency else None,
                confidence=confidence if is_valid_emergency else 0.0,
                reason="Holding active confirmation",
            )

        return DebounceResult(
            confirmed=False,
            dominant_class=None,
            confidence=confidence,
            reason=f"Unconfirmed: {total_emergency_frames}/{self.confirm_k} frames needed",
        )
