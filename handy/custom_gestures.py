"""
Custom gesture definitions, recording, and matching.

Matching algorithm
------------------
Landmarks are normalized relative to the wrist (landmark 0) and scaled
by the wrist→mid-MCP (landmark 9) distance, making templates invariant
to hand position and size.  The L2 distance between the query and each
template's mean is computed across all 21 landmarks; the closest template
wins if it is below MATCH_THRESHOLD.

Built-in gesture registry
--------------------------
BUILTIN_ENTRIES lists the gesture names produced by gesture.classify_gesture()
so the action system can bind actions to them without any recording needed.
Code-embedded custom gestures can be added to BUILTIN_ENTRIES at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ── Matching sensitivity ───────────────────────────────────────────────────
MATCH_THRESHOLD: float = 0.20     # max average per-landmark distance for a hit
MIN_SAMPLES: int = 15             # minimum snapshots before a template is usable
RECORD_SAMPLES: int = 30          # target number of training frames


# ── Built-in gestures (produced by gesture.classify_gesture) ──────────────
# Add code-embedded gesture names here in the future.
BUILTIN_ENTRIES: list[str] = [
    "Fist",
    "Open Hand",
    "One Finger",
    "Victory",
    "Hang Loose",
    "Thumbs Up",
    "1 Fingers",
    "2 Fingers",
    "3 Fingers",
    "4 Fingers",
    "5 Fingers",
    # ── Placeholder: add future code-defined gesture names below ──────────
]


# ── Data model ─────────────────────────────────────────────────────────────

@dataclass
class GestureTemplate:
    """One named gesture with one or more normalized landmark snapshots."""

    name: str
    samples: list = field(default_factory=list)   # list of np.ndarray (21, 2)

    # ── Serialization ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "samples": [s.tolist() for s in self.samples],
        }

    @staticmethod
    def from_dict(d: dict) -> "GestureTemplate":
        return GestureTemplate(
            name=d["name"],
            samples=[np.array(s, dtype=np.float32) for s in d.get("samples", [])],
        )

    # ── Training helpers ───────────────────────────────────────────────────

    def is_trained(self) -> bool:
        return len(self.samples) >= MIN_SAMPLES

    def sample_count(self) -> int:
        return len(self.samples)

    def mean_template(self) -> Optional[np.ndarray]:
        """Return (21, 2) mean of all samples, or None if untrained."""
        if not self.samples:
            return None
        return np.mean(np.stack(self.samples), axis=0)

    def add_sample(self, lm_list: list) -> bool:
        """Normalize lm_list and append; return True on success."""
        norm = normalize_landmarks(lm_list)
        if norm is None:
            return False
        self.samples.append(norm)
        return True

    def clear_samples(self) -> None:
        self.samples.clear()


# ── Normalization ──────────────────────────────────────────────────────────

def normalize_landmarks(lm_list: list) -> Optional[np.ndarray]:
    """
    Convert raw landmark list to a scale/position-invariant (21, 2) array.

    lm_list: list of (x, y, z) tuples with x/y in [0, 1].
    Origin  = wrist (landmark 0).
    Scale   = wrist → mid-MCP (landmark 9) distance.
    Returns None when the hand is too small or degenerate.
    """
    pts = np.array([[lm[0], lm[1]] for lm in lm_list], dtype=np.float32)
    pts -= pts[0]                                   # translate to wrist origin
    hand_size = float(np.linalg.norm(pts[9]))       # scale reference
    if hand_size < 1e-4:
        return None
    pts /= hand_size
    return pts


# ── Matching ───────────────────────────────────────────────────────────────

def match_custom_gesture(
    lm_list: list,
    templates: list,          # list[GestureTemplate]
) -> Optional[str]:
    """
    Return the name of the closest trained GestureTemplate below threshold,
    or None if no match.
    """
    norm = normalize_landmarks(lm_list)
    if norm is None:
        return None

    best_name: Optional[str] = None
    best_dist: float = MATCH_THRESHOLD

    for tmpl in templates:
        mean = tmpl.mean_template()
        if mean is None:
            continue
        dist = float(np.mean(np.linalg.norm(norm - mean, axis=1)))
        if dist < best_dist:
            best_dist = dist
            best_name = tmpl.name

    return best_name
