"""内容ハッシュと描画仕様で検証するPSD単位の永続キャッシュ。"""

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from uuid import uuid4

import PIL
import psd_tools
from PIL import Image
from psd_tools import PSDImage

from . import performance_log as perf

MAX_SIDE = 1400
RENDER_REVISION = 1
CACHE_KIND = "psd-mascot-cache"


def state_digest(state):
    data = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _atomic_json(path, value):
    temporary = path.with_name(f"{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _safe_child(root, directory):
    root = Path(root).resolve()
    directory = Path(directory)
    if not re.fullmatch(r"[0-9a-f]{24}", directory.name):
        raise ValueError("キャッシュの識別子が正しくありません")
    if directory.is_symlink() or directory.is_junction() or directory.resolve().parent != root:
        raise ValueError("キャッシュフォルダの外は操作できません")
    return directory.resolve()


class DocumentCache:
    def __init__(self, root, source, source_digest, canvas_size):
        self.root = Path(root)
        self.source = Path(source).resolve()
        self.document_id = hashlib.sha256(str(self.source).casefold().encode("utf-8")).hexdigest()[:24]
        self.directory = self.root / self.document_id
        self.source_digest = source_digest
        self.canvas_size = tuple(canvas_size)
        self.render_signature = {
            "revision": RENDER_REVISION, "max_side": MAX_SIDE, "format": "RGBA",
            "psd_tools": psd_tools.__version__, "pillow": PIL.__version__,
        }
        generation = json.dumps([source_digest, self.render_signature], sort_keys=True).encode("utf-8")
        self.generation_id = hashlib.sha256(generation).hexdigest()[:24]
        self.frames_directory = self.directory / self.generation_id
        self.last_error = ""

    def prepare(self):
        self.root.mkdir(parents=True, exist_ok=True)
        _safe_child(self.root, self.directory)
        self.directory.mkdir(exist_ok=True)
        _safe_child(self.directory, self.frames_directory)
        self.frames_directory.mkdir(exist_ok=True)
        _atomic_json(self.directory / "metadata.json", {
            "kind": CACHE_KIND, "schema": 1, "document_id": self.document_id,
            "psd_name": self.source.name, "psd_path": str(self.source),
            "last_used": time.time(),
        })
        _atomic_json(self.frames_directory / "generation.json", {
            "source_sha256": self.source_digest, "renderer": self.render_signature,
            "canvas_size": self.canvas_size,
        })

    def frame_path(self, state):
        return self.frames_directory / f"{state_digest(state)}.png"

    def read(self, state):
        with perf.measure("cache_read_validate"):
            image = self._read_unmeasured(state)
        perf.count("cache_validation_valid" if image is not None else "cache_validation_missing_or_invalid")
        return image

    def _read_unmeasured(self, state):
        path = self.frame_path(state)
        try:
            _safe_child(self.root, self.directory)
            _safe_child(self.directory, self.frames_directory)
            if path.is_symlink():
                return None
            with Image.open(path) as image:
                if image.format != "PNG" or image.mode != "RGBA":
                    return None
                if image.width < 1 or image.height < 1 or max(image.size) > MAX_SIDE:
                    return None
                # Validate dimensions as well as the file's metadata/contents.
                width, height = self.canvas_size
                ratio = min(1.0, MAX_SIDE/max(width, height))
                if abs(image.width-width*ratio) > 1.1 or abs(image.height-height*ratio) > 1.1:
                    return None
                image.load()
                return image.copy()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            return None

    def contains_valid(self, state):
        image = self.read(state)
        if image is None:
            return False
        image.close()
        return True

    def write(self, state, image):
        if not self.frames_directory.exists():
            self.prepare()
        _safe_child(self.root, self.directory)
        _safe_child(self.directory, self.frames_directory)
        target = self.frame_path(state)
        temporary = self.frames_directory / f"{uuid4().hex}.tmp"
        try:
            with perf.measure("png_save"):
                image.save(temporary, format="PNG")
                temporary.replace(target)
            self.last_error = ""
        finally:
            if temporary.exists():
                temporary.unlink()


class CacheRegistry:
    def __init__(self, root):
        self.root = Path(root)

    def ensure(self):
        self.root.mkdir(parents=True, exist_ok=True)

    def load_document(self, source):
        """Hash and parsing run in the rendering worker, never in the GUI thread."""
        source = Path(source).resolve()
        before = source.stat()
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
        psd = PSDImage.open(source)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise OSError("読み込み中にPSDが変更されました。もう一度開いてください")
        cache = DocumentCache(self.root, source, digest.hexdigest(), (psd.width, psd.height))
        try:
            cache.prepare()
        except (OSError, ValueError) as exc:
            cache.last_error = str(exc)
        return psd, cache

    def _metadata(self, directory):
        directory = _safe_child(self.root, directory)
        metadata_path = directory / "metadata.json"
        if metadata_path.is_symlink():
            raise ValueError("不正なキャッシュ管理情報です")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("kind") != CACHE_KIND or metadata.get("document_id") != directory.name:
            raise ValueError("アプリが作成したキャッシュではありません")
        return metadata

    def list_documents(self):
        self.ensure()
        result = []
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                metadata = self._metadata(directory)
                count = size = 0
                for parent, dirs, files in os.walk(directory, followlinks=False):
                    dirs[:] = [name for name in dirs if not (Path(parent)/name).is_symlink()
                               and not (Path(parent)/name).is_junction()]
                    for name in files:
                        file = Path(parent) / name
                        if file.is_symlink():
                            continue
                        size += file.stat().st_size
                        count += int(file.suffix.lower() == ".png")
                result.append({**metadata, "frames": count, "bytes": size})
            except (OSError, ValueError, AttributeError):
                continue
        return sorted(result, key=lambda value: (value.get("psd_name", ""), value.get("psd_path", "")))

    def delete_documents(self, identifiers):
        targets = []
        for identifier in identifiers:
            directory = _safe_child(self.root, self.root / identifier)
            self._metadata(directory)
            targets.append((identifier, directory))
        deleted, errors = [], []
        for identifier, directory in targets:
            try:
                # Resolved targets are validated direct children of this root.
                shutil.rmtree(directory)
                deleted.append(identifier)
            except OSError as exc:
                errors.append(str(exc))
        return {"deleted": deleted, "errors": errors}
