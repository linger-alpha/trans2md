from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from trans2md.models import ConvertResult

IMAGE_REF_PATTERN = re.compile(r"(!\[[^\]]*]\()([^)]+)(\))")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
JSON_PRIORITY = ("content_list", "middle", "model")


class ArtifactError(RuntimeError):
    """MinerU 产物整理失败。"""


class ArtifactWriter:
    def __init__(self, *, keep_zip: bool, export_json: bool, overwrite: bool, layout: str) -> None:
        self.keep_zip = keep_zip
        self.export_json = export_json
        self.overwrite = overwrite
        self.layout = layout

    def materialize(self, source_path: Path, zip_path: Path) -> ConvertResult:
        with TemporaryDirectory(prefix="trans2md_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(temp_dir)

            markdown_source = self._pick_markdown(temp_dir)
            markdown_text = markdown_source.read_text(encoding="utf-8")

            # Decide final layout (auto may choose minimal output when there are no images).
            has_images = self._markdown_has_local_images(markdown_text)
            markdown_path, image_copy_root, image_dir_for_result, json_path, kept_zip_path = (
                self._compute_paths(source_path, has_images=has_images)
            )

            self._ensure_writable(markdown_path)
            if self.export_json and json_path is not None:
                self._ensure_writable(json_path)
            if self.keep_zip and kept_zip_path is not None:
                self._ensure_writable(kept_zip_path)

            # Backward-compat cleanup: older versions used "<out>/img/images/...".
            # Only remove this when we are writing into the bundle directory.
            if self.overwrite and self.layout in {"bundle", "auto"} and has_images:
                legacy_img_dir = markdown_path.parent / "img"
                if legacy_img_dir.exists() and legacy_img_dir.is_dir():
                    shutil.rmtree(legacy_img_dir)

            if image_dir_for_result and image_dir_for_result.exists():
                if not self.overwrite:
                    raise ArtifactError(f"图片目录已存在：{image_dir_for_result}")
                shutil.rmtree(image_dir_for_result)

            rewritten_markdown = self._rewrite_markdown_images(
                markdown_text=markdown_text,
                markdown_source=markdown_source,
                extraction_root=temp_dir,
                image_copy_root=image_copy_root,
            )
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(rewritten_markdown, encoding="utf-8")

            if self.export_json and json_path is not None:
                json_source = self._pick_json(temp_dir)
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_path.write_text(json_source.read_text(encoding="utf-8"), encoding="utf-8")

        if self.keep_zip and kept_zip_path is not None:
            kept_zip_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(zip_path, kept_zip_path)

        return ConvertResult(
            source_path=source_path,
            markdown_path=markdown_path,
            image_dir=(
                image_dir_for_result
                if (image_dir_for_result and image_dir_for_result.exists())
                else None
            ),
            json_path=json_path if json_path and json_path.exists() else None,
            zip_path=kept_zip_path if kept_zip_path and kept_zip_path.exists() else None,
        )

    def _compute_paths(
        self, source_path: Path, *, has_images: bool
    ) -> tuple[Path, Path | None, Path | None, Path | None, Path | None]:
        """
        Returns:
        - markdown_path
        - image_copy_root: where referenced assets are copied to (may be None)
        - image_dir_for_result: what we report back to the caller as "image_dir" (may be None)
        - json_path
        - kept_zip_path
        """
        if self.layout == "bundle":
            out_dir = source_path.with_name(f"{source_path.stem}_trans2md")
            markdown_path = out_dir / f"{source_path.stem}.md"
            # Keep MinerU's default relative directory structure (e.g. "images/...") next to the md.
            # We copy referenced assets into out_dir and keep markdown references unchanged.
            image_copy_root = out_dir
            json_path = out_dir / f"{source_path.stem}.json" if self.export_json else None
            kept_zip_path = (
                out_dir / f"{source_path.stem}_mineru.zip" if self.keep_zip else None
            )
            image_dir_for_result = out_dir / "images"
            return markdown_path, image_copy_root, image_dir_for_result, json_path, kept_zip_path

        if self.layout == "auto":
            if has_images:
                out_dir = source_path.with_name(f"{source_path.stem}_trans2md")
                markdown_path = out_dir / f"{source_path.stem}.md"
                image_copy_root = out_dir
                json_path = out_dir / f"{source_path.stem}.json" if self.export_json else None
                kept_zip_path = (
                    out_dir / f"{source_path.stem}_mineru.zip" if self.keep_zip else None
                )
                image_dir_for_result = out_dir / "images"
                return (
                    markdown_path,
                    image_copy_root,
                    image_dir_for_result,
                    json_path,
                    kept_zip_path,
                )

            # No images: keep it simple and write <stem>.md next to the source file.
            markdown_path = source_path.with_suffix(".md")
            json_path = source_path.with_suffix(".json") if self.export_json else None
            kept_zip_path = (
                source_path.with_name(f"{source_path.stem}_mineru.zip") if self.keep_zip else None
            )
            return markdown_path, None, None, json_path, kept_zip_path

        raise ArtifactError(f"未知输出布局：{self.layout}")

    def _rewrite_markdown_images(
        self,
        *,
        markdown_text: str,
        markdown_source: Path,
        extraction_root: Path,
        image_copy_root: Path | None,
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            raw_target = match.group(2).strip()
            if not raw_target or raw_target.startswith(("http://", "https://", "data:")):
                return match.group(0)

            normalized_target = PurePosixPath(raw_target)
            source_asset = (markdown_source.parent / Path(*normalized_target.parts)).resolve()
            try:
                source_asset.relative_to(extraction_root.resolve())
            except ValueError as exc:
                raise ArtifactError(f"Markdown 引用了压缩包外部资源：{raw_target}") from exc
            if not source_asset.exists():
                raise ArtifactError(f"Markdown 引用的资源不存在：{raw_target}")

            if image_copy_root is not None:
                destination = image_copy_root.joinpath(*normalized_target.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_asset, destination)

            # Keep original relative references (e.g. "images/...") and only copy assets.
            return match.group(0)

        rewritten = IMAGE_REF_PATTERN.sub(replace, markdown_text)
        return rewritten

    @staticmethod
    def _markdown_has_local_images(markdown_text: str) -> bool:
        for match in IMAGE_REF_PATTERN.finditer(markdown_text):
            raw_target = match.group(2).strip()
            if not raw_target or raw_target.startswith(("http://", "https://", "data:")):
                continue
            suffix = Path(PurePosixPath(raw_target).name).suffix.lower()
            if suffix in IMAGE_SUFFIXES:
                return True
        return False

    @staticmethod
    def _pick_markdown(extraction_root: Path) -> Path:
        candidates = sorted(extraction_root.rglob("*.md"))
        if not candidates:
            raise ArtifactError("结果 ZIP 中未找到 Markdown 文件")
        return min(candidates, key=lambda path: (len(path.parts), path.name))

    @staticmethod
    def _pick_json(extraction_root: Path) -> Path:
        candidates = sorted(extraction_root.rglob("*.json"))
        if not candidates:
            raise ArtifactError("结果 ZIP 中未找到 JSON 文件")
        for key in JSON_PRIORITY:
            for candidate in candidates:
                if candidate.name.endswith(f"_{key}.json"):
                    return candidate
        return min(candidates, key=lambda path: (len(path.parts), path.name))

    def _ensure_writable(self, path: Path) -> None:
        if path.exists() and not self.overwrite:
            raise ArtifactError(f"输出文件已存在：{path}")
