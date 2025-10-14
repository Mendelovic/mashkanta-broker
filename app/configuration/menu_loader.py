
"""Utilities for loading Bank of Israel average mortgage rate menus."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Dict, Mapping, Sequence

import yaml

logger = logging.getLogger(__name__)

MENU_FILENAME = "average_menu_boi.yaml"
CANONICAL_TO_TRACK_KEY = {
    "variable_prime": "variable_prime",
    "variable_unlinked": "variable_unindexed",
    "fixed_unindexed": "fixed_unindexed",
    "variable_cpi": "variable_cpi",
    "fixed_cpi": "fixed_cpi",
}


def _collect_midpoints(node: object) -> Sequence[float]:
    midpoints: list[float] = []

    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in {"canonical_type", "baseline_midpoint_pct"}:
                continue
            midpoints.extend(_collect_midpoints(value))
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        if len(node) == 2 and all(isinstance(v, (int, float)) for v in node):
            midpoints.append((float(node[0]) + float(node[1])) / 2)
        else:
            for item in node:
                midpoints.extend(_collect_midpoints(item))

    return midpoints


@lru_cache(maxsize=1)
def load_average_menu_rates(base_path: Path | None = None) -> Dict[str, float]:
    """Return default annual rates (decimals) per canonical track."""

    location = base_path or Path(__file__).resolve().parent.parent / "config" / MENU_FILENAME
    try:
        data = yaml.safe_load(location.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Average market menu file not found: %s", location)
        return {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to load average market menu: %s", exc)
        return {}

    if not isinstance(data, Mapping):
        logger.warning("Average market menu file has unexpected structure")
        return {}

    tracks = data.get("tracks")
    if not isinstance(tracks, Mapping):
        logger.warning("Average market menu 'tracks' section malformed")
        return {}

    results: Dict[str, float] = {}

    for _, track_data in tracks.items():
        if not isinstance(track_data, Mapping):
            continue

        canonical = track_data.get("canonical_type")
        canonical_str = str(canonical) if canonical is not None else ""
        target_key = CANONICAL_TO_TRACK_KEY.get(canonical_str)
        if not target_key:
            continue

        baseline = track_data.get("baseline_midpoint_pct")
        rate_decimal = None
        if isinstance(baseline, (int, float)):
            rate_decimal = float(baseline) / 100.0
        else:
            midpoints = _collect_midpoints(track_data)
            if midpoints:
                rate_decimal = mean(midpoints) / 100.0

        if rate_decimal is None or rate_decimal <= 0:
            logger.warning("No usable rate found for track %s", canonical_str)
            continue

        results[target_key] = rate_decimal

    return results


__all__ = ["load_average_menu_rates"]
