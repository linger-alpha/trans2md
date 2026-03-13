from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InstallTargetPaths:
    codex_user_skills: Path
    claude_user_skills: Path
    openclaw_user_skills: Path


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists() and path.is_dir():
            return path
    return None


def detect_codex_user_skills_dir(home: Path) -> Path:
    """
    Prefer Codex's current default (~/.codex/skills). Fallback to the older (~/.agents/skills)
    if it exists. If neither exists, return the preferred default (so the caller can create it).
    """
    preferred = home / ".codex" / "skills"
    legacy = home / ".agents" / "skills"
    existing = _first_existing([preferred, legacy])
    return existing or preferred


def detect_openclaw_user_skills_dir(home: Path) -> Path:
    """
    Prefer OpenClaw workspace skills if present, otherwise use managed skills.
    If neither exists, return the managed skills default (~/.openclaw/skills).
    """
    workspace = home / ".openclaw" / "workspace" / "skills"
    managed = home / ".openclaw" / "skills"
    existing = _first_existing([workspace, managed])
    return existing or managed


def default_targets(home: Path) -> InstallTargetPaths:
    return InstallTargetPaths(
        codex_user_skills=detect_codex_user_skills_dir(home),
        claude_user_skills=home / ".claude" / "skills",
        openclaw_user_skills=detect_openclaw_user_skills_dir(home),
    )


def copy_skill_bundle(skill_name: str, destination_root: Path, *, overwrite: bool) -> Path:
    bundle_root = resources.files("trans2md").joinpath("skill_bundle")
    source = bundle_root.joinpath(skill_name)
    if not source.is_dir():
        raise FileNotFoundError(f"未找到内置 skill 模板：{skill_name}")

    destination = destination_root / skill_name
    if destination.exists():
        if not overwrite:
            raise FileExistsError(f"目标已存在：{destination}")
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return destination
