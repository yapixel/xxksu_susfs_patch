"""Content and source-tree hashing with a stable, path-independent contract."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..model.provenance import HashDigest


class UnsafePath(ValueError):
    pass


def validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise UnsafePath("invalid relative path")
    path = value.replace("\\", "/")
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        raise UnsafePath("absolute path is not allowed")
    parts = [part for part in path.split("/") if part not in ("", ".")]
    if ".." in parts:
        raise UnsafePath("path traversal is not allowed")
    return "/".join(parts)


def hash_bytes(data: bytes) -> HashDigest:
    return HashDigest("sha256", hashlib.sha256(data).hexdigest())


def hash_file(path: os.PathLike[str] | str) -> HashDigest:
    with Path(path).open("rb") as handle:
        digest = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return HashDigest("sha256", digest.hexdigest())


def hash_tree(root: os.PathLike[str] | str) -> HashDigest:
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("tree root must be a real directory")
    digest = hashlib.sha256()
    entries: list[tuple[str, Path, str]] = []
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(name for name in dirs if name != ".git")
        for name in sorted(files):
            path = current_path / name
            rel = path.relative_to(root).as_posix()
            entries.append((rel, path, "symlink" if path.is_symlink() else "file"))
        for name in list(dirs):
            path = current_path / name
            if path.is_symlink():
                dirs.remove(name)
                entries.append((path.relative_to(root).as_posix(), path, "symlink"))
            else:
                entries.append((path.relative_to(root).as_posix(), path, "dir"))
    for rel, path, kind in sorted(entries, key=lambda item: item[0]):
        rel_bytes = rel.encode("utf-8")
        if kind == "dir":
            record = b"dir\0" + str(len(rel_bytes)).encode() + b":" + rel_bytes + b"\n"
        elif kind == "symlink":
            target = os.readlink(path).encode("utf-8")
            record = b"symlink\0" + str(len(rel_bytes)).encode() + b":" + rel_bytes + b"\0" + str(len(target)).encode() + b":" + target + b"\n"
        else:
            content = path.read_bytes()
            executable = b"x" if path.stat().st_mode & 0o111 else b"-"
            record = b"file" + executable + b"\0" + str(len(rel_bytes)).encode() + b":" + rel_bytes + b"\0" + str(len(content)).encode() + b":" + content + b"\n"
        digest.update(record)
    return HashDigest("sha256", digest.hexdigest())
