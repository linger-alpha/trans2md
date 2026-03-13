from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path


@dataclass(frozen=True, slots=True)
class AppConfig:
    mineru_api_token: str | None = None


def get_config_file() -> Path:
    config_dir = Path(user_config_path("trans2md", appauthor=False))
    return config_dir / "config.json"


def load_config() -> AppConfig:
    path = get_config_file()
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AppConfig()
    if not isinstance(raw, dict):
        return AppConfig()
    token = raw.get("mineru_api_token")
    if isinstance(token, str) and token.strip():
        return AppConfig(mineru_api_token=token.strip())
    return AppConfig()


def save_token(token: str) -> Path:
    token = token.strip()
    if not token:
        raise ValueError("token 不能为空")
    path = get_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mineru_api_token": token}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def clear_token() -> Path:
    path = get_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path

