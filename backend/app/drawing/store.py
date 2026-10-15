"""Transient drawing-analysis artifacts with bounded retention."""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ANALYSIS_ID = re.compile(r"^[a-f0-9]{32}$")
DEFAULT_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class StoredAnalysis:
    analysis_id: str
    directory: Path

    @property
    def image_path(self) -> Path:
        return self.directory / "normalized.png"

    @property
    def overlay_path(self) -> Path:
        return self.directory / "overlay.svg"

    @property
    def profile_path(self) -> Path:
        return self.directory / "profile.json"


def create_analysis(
    root: Path, *, normalized_png: bytes, overlay: str, profile: dict[str, Any]
) -> StoredAnalysis:
    root.mkdir(parents=True, exist_ok=True)
    analysis_id = uuid.uuid4().hex
    directory = root / analysis_id
    directory.mkdir()
    stored = StoredAnalysis(analysis_id, directory)
    stored.image_path.write_bytes(normalized_png)
    stored.overlay_path.write_text(overlay, encoding="utf-8")
    stored.profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stored


def get_analysis(root: Path, analysis_id: str) -> StoredAnalysis | None:
    if not ANALYSIS_ID.fullmatch(analysis_id):
        return None
    stored = StoredAnalysis(analysis_id, root / analysis_id)
    if not (
        stored.directory.is_dir()
        and stored.image_path.is_file()
        and stored.overlay_path.is_file()
        and stored.profile_path.is_file()
    ):
        return None
    return stored


def cleanup_analyses(
    root: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, now: float | None = None
) -> int:
    if not root.is_dir():
        return 0
    cutoff = (time.time() if now is None else now) - ttl_seconds
    removed = 0
    for candidate in root.iterdir():
        if candidate.is_dir() and ANALYSIS_ID.fullmatch(candidate.name):
            if candidate.stat().st_mtime < cutoff:
                shutil.rmtree(candidate)
                removed += 1
    return removed
