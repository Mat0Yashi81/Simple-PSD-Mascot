"""Worker-local, observational cache timings. Never changes cache keys or pixels."""

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4


STAGES = {
    "psd_composite": "PSD全体の合成",
    "region_composite": "変更領域のPSD再合成",
    "fast_render": "高速経路全体（領域合成・RGBA変換等を内包）",
    "fallback_render": "従来方式への切り戻し（全体合成・RGBA変換を内包）",
    "rgba_convert": "RGBA変換",
    "resize": "長辺1400pxへの縮小（縮小不要時の呼び出しも含む）",
    "png_save": "PNGエンコード・ファイル保存（一時ファイル置換を含む）",
    "cache_read_validate": "既存PNGの読み込み・検証（未存在の確認を含む）",
    "total": "処理全体",
}
_local = threading.local()
_directory = None
_enabled = False


def configure(directory):
    global _directory
    _directory = Path(directory)


def set_enabled(enabled):
    global _enabled
    _enabled = bool(enabled)


def is_enabled():
    return _enabled


def current():
    return getattr(_local, "session", None)


def count(name):
    session = current()
    if session is not None:
        session["counters"][name] = session["counters"].get(name, 0) + 1


def event(name, **details):
    data = current()
    if data is not None:
        events = data.setdefault("events", [])
        if len(events) < 64:
            events.append({"name": name, **details})
        else:
            count("debug_events_truncated")


def _add(session, name, elapsed, failed=False):
    stat = session["stages"][name]
    stat["count"] += 1
    stat["total_seconds"] += elapsed
    stat["max_seconds"] = max(stat["max_seconds"], elapsed)
    stat["failed_count"] += int(failed)


@contextmanager
def measure(name):
    session = current()
    if session is None:
        yield
        return
    started = time.perf_counter()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        _add(session, name, time.perf_counter() - started, failed)


def _write(session):
    # Logging failure must not turn a successful render into a failed render.
    if not _enabled:
        return
    filename = f"cache-performance-{datetime.now():%Y%m%d-%H%M%S-%f}-{os.getpid()}-{uuid4().hex[:8]}.json"
    for directory in (_directory, Path(tempfile.gettempdir()) / "PSD-Mascot" / "logs"):
        if directory is None:
            continue
        try:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / filename).write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
            return
        except (OSError, ValueError):
            continue


@contextmanager
def session(kind, source=None, **metadata):
    if current() is not None:
        yield current()
        return
    if not _enabled:
        # Callers may attach a result to the yielded mapping; no timing state
        # or file is needed when the user has opted out of diagnostics.
        yield {}
        return
    logging_at_start = _enabled
    data = {
        "schema": 1, "app_version": "1.0.1", "kind": kind,
        "started_at": datetime.now().astimezone().isoformat(),
        "source": str(source) if source is not None else None,
        "metadata": metadata, "status": "completed",
        "stages": {key: {"label": label, "count": 0, "total_seconds": 0.0,
                          "average_seconds": 0.0, "max_seconds": 0.0, "failed_count": 0}
                   for key, label in STAGES.items()},
        "counters": {}, "frames": [],
    }
    _local.session = data
    started = time.perf_counter()
    try:
        yield data
    except BaseException as exc:
        data["status"] = "failed"
        data["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _add(data, "total", time.perf_counter() - started, data["status"] == "failed")
        for stat in data["stages"].values():
            if stat["count"]:
                stat["average_seconds"] = stat["total_seconds"] / stat["count"]
        _local.session = None
        # Animation commonly reuses RAM frames every 120 ms. Avoid introducing
        # disk writes on that hot path; bulk sessions still count RAM reuse.
        if logging_at_start and _enabled and (kind != "frame" or data["status"] == "failed" or any(
                data["stages"][key]["count"] for key in
                ("psd_composite", "region_composite", "cache_read_validate", "png_save"))):
            _write(data)


@contextmanager
def frame(identifier):
    data = current()
    if data is None:
        yield {"state_digest": identifier, "source": "failed"}
        return
    before = {key: value["total_seconds"] for key, value in data["stages"].items()}
    record = {"state_digest": identifier, "source": "failed"}
    started = time.perf_counter()
    try:
        yield record
    finally:
        record["elapsed_seconds"] = time.perf_counter() - started
        record["stage_seconds"] = {key: value["total_seconds"] - before[key]
                                   for key, value in data["stages"].items() if key != "total"}
        data["frames"].append(record)
