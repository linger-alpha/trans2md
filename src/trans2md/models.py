from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class LocalFileJob:
    source_path: Path
    data_id: str


@dataclass(slots=True)
class UploadBatch:
    batch_id: str
    file_urls: list[str]


@dataclass(slots=True)
class BatchFileResult:
    file_name: str
    state: str
    err_msg: str
    full_zip_url: str | None = None
    data_id: str | None = None


@dataclass(slots=True)
class ConvertResult:
    source_path: Path
    markdown_path: Path
    image_dir: Path | None
    json_path: Path | None
    zip_path: Path | None
