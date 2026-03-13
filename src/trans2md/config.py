from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path


@dataclass(frozen=True, slots=True)
class AppConfig:
    mineru_api_token: str | None = None
    # target -> list of installed skill directory paths
    installed_skills: dict[str, list[str]] | None = None


def get_config_dir() -> Path:
    return Path(user_config_path("trans2md", appauthor=False))


def get_config_file() -> Path:
    return get_config_dir() / "config.json"


def _load_raw() -> dict:
    path = get_config_file()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_raw(raw: dict) -> Path:
    path = get_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _clean_installed_skills(raw_installed: object) -> dict[str, list[str]] | None:
    if not isinstance(raw_installed, dict):
        return None
    cleaned: dict[str, list[str]] = {}
    for key, value in raw_installed.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, list):
            continue
        items: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
        if items:
            cleaned[key] = sorted(set(items))
    return cleaned or None


def load_config() -> AppConfig:
    raw = _load_raw()

    token = raw.get("mineru_api_token")
    token_value = token.strip() if isinstance(token, str) and token.strip() else None

    installed_skills = _clean_installed_skills(raw.get("installed_skills"))

    return AppConfig(mineru_api_token=token_value, installed_skills=installed_skills)


def save_token(token: str) -> Path:
    token = token.strip()
    if not token:
        raise ValueError("token 不能为空")
    raw = _load_raw()
    raw["mineru_api_token"] = token
    return _write_raw(raw)


def clear_token() -> Path:
    raw = _load_raw()
    raw.pop("mineru_api_token", None)
    return _write_raw(raw)


def record_skill_install(target: str, skill_dir: Path) -> Path:
    raw = _load_raw()
    installed = raw.get("installed_skills")
    if not isinstance(installed, dict):
        installed = {}

    paths = installed.get(target)
    if not isinstance(paths, list):
        paths = []
    paths.append(str(skill_dir))

    installed[target] = sorted(set([p for p in paths if isinstance(p, str) and p.strip()]))
    raw["installed_skills"] = installed
    return _write_raw(raw)


def clear_all_config() -> None:
    """
    Remove all trans2md local configuration (token + install records).
    """
    config_file = get_config_file()
    try:
        if config_file.exists():
            config_file.unlink()
    except OSError:
        return

    # Best-effort: remove the directory if empty.
    try:
        config_dir = config_file.parent
        if config_dir.exists() and config_dir.is_dir() and not any(config_dir.iterdir()):
            config_dir.rmdir()
    except OSError:
        return

