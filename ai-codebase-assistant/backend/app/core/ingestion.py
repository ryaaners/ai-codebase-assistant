"""
Gets a repository from the outside world (GitHub URL or an uploaded ZIP)
onto local disk as a plain directory, then enumerates the files worth
parsing. Nothing in here understands code -- that's extractor.py's job.
"""
from __future__ import annotations

import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import git

from app.core.parser import IGNORED_DIR_NAMES, detect_language

GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(\.git)?/?$"
)


class IngestionError(ValueError):
    pass


@dataclass
class RepoFile:
    abs_path: Path
    rel_path: str  # posix-style, relative to repo root
    language: str | None
    size_bytes: int


def validate_github_url(url: str) -> tuple[str, str]:
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise IngestionError(
            "That doesn't look like a GitHub repo URL. Expected something like "
            "https://github.com/owner/repo"
        )
    return match.group("owner"), match.group("repo")


def clone_github_repo(url: str, dest_dir: Path, *, depth: int = 1) -> Path:
    """Shallow-clones a public GitHub repo. dest_dir must not already exist."""
    owner, repo = validate_github_url(url)
    if dest_dir.exists():
        raise IngestionError(f"Destination already exists: {dest_dir}")
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        git.Repo.clone_from(f"https://github.com/{owner}/{repo}.git", dest_dir, depth=depth)
    except git.GitCommandError as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise IngestionError(
            f"Could not clone {url}. It may be private, deleted, or rate-limited."
        ) from exc
    return dest_dir


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Unpacks an uploaded ZIP, guarding against path traversal (zip-slip) and
    collapsing a single top-level wrapper folder (GitHub's 'Download ZIP'
    always wraps everything in `<repo>-<branch>/`)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            member_path = (dest_dir / member).resolve()
            if not str(member_path).startswith(str(dest_dir.resolve())):
                raise IngestionError(f"Unsafe path in ZIP: {member}")
        zf.extractall(dest_dir)

    entries = [p for p in dest_dir.iterdir() if not p.name.startswith("__MACOSX")]
    if len(entries) == 1 and entries[0].is_dir():
        wrapper = entries[0]
        for item in wrapper.iterdir():
            shutil.move(str(item), str(dest_dir / item.name))
        wrapper.rmdir()
    return dest_dir


def walk_repository(
    root: Path, *, max_file_size_bytes: int = 500_000, max_files: int = 20_000
) -> list[RepoFile]:
    """Enumerates files under root, skipping ignored dirs, binaries, and
    anything oversized. Files in a language we don't parse are still
    returned (language=None) so the file explorer can show the whole tree,
    but indexing skips them."""
    results: list[RepoFile] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_file_size_bytes:
            continue
        rel = path.relative_to(root).as_posix()
        results.append(
            RepoFile(abs_path=path, rel_path=rel, language=detect_language(rel), size_bytes=size)
        )
        if len(results) >= max_files:
            break
    return results


def detect_primary_languages(files: list[RepoFile]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in files:
        if f.language:
            counts[f.language] = counts.get(f.language, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
