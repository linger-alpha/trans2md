from __future__ import annotations

import zipfile
from pathlib import Path

from trans2md.artifacts import ArtifactWriter


def _build_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("bundle/demo.md", "hello\n\n![img](images/page1.png)\n")
        archive.writestr("bundle/images/page1.png", b"fake-image")
        archive.writestr("bundle/demo_content_list.json", '{"kind": "content_list"}')
        archive.writestr("bundle/demo_middle.json", '{"kind": "middle"}')


def test_materialize_bundle_layout(tmp_path: Path) -> None:
    source_path = tmp_path / "demo.pdf"
    source_path.write_bytes(b"pdf")
    zip_path = tmp_path / "result.zip"
    _build_zip(zip_path)

    writer = ArtifactWriter(keep_zip=False, export_json=False, overwrite=False, layout="bundle")
    result = writer.materialize(source_path, zip_path)

    expected_dir = tmp_path / "demo_trans2md"
    assert result.markdown_path == expected_dir / "demo.md"
    assert result.image_dir == expected_dir / "images"
    assert result.markdown_path.read_text(encoding="utf-8") == "hello\n\n![img](images/page1.png)\n"
    assert (expected_dir / "images" / "page1.png").read_bytes() == b"fake-image"


def test_materialize_auto_layout_no_images_writes_next_to_source(tmp_path: Path) -> None:
    source_path = tmp_path / "demo.pdf"
    source_path.write_bytes(b"pdf")

    zip_path = tmp_path / "result.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("bundle/demo.md", "hello\n")
        archive.writestr("bundle/demo_content_list.json", '{"kind": "content_list"}')

    writer = ArtifactWriter(keep_zip=False, export_json=False, overwrite=False, layout="auto")
    result = writer.materialize(source_path, zip_path)

    assert result.markdown_path == tmp_path / "demo.md"
    assert result.markdown_path.read_text(encoding="utf-8") == "hello\n"
    assert result.image_dir is None
    assert not (tmp_path / "demo_trans2md").exists()
