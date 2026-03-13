from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import typer

from trans2md import __version__
from trans2md.artifacts import ArtifactError, ArtifactWriter
from trans2md.config import (
    clear_all_config,
    clear_token,
    load_config,
    record_skill_install,
    save_token,
)
from trans2md.installer import (
    codex_skill_root_candidates,
    copy_skill_bundle,
    default_targets,
    openclaw_skill_root_candidates,
)
from trans2md.mineru_api import MineruApiError, MineruClient
from trans2md.models import BatchFileResult, LocalFileJob

_CTX = {"help_option_names": ["-h", "--help"]}

app = typer.Typer(add_completion=False, no_args_is_help=True, context_settings=_CTX)
auth_app = typer.Typer(add_completion=False, no_args_is_help=True, context_settings=_CTX)
install_app = typer.Typer(add_completion=False, no_args_is_help=True, context_settings=_CTX)

app.add_typer(auth_app, name="auth")
app.add_typer(install_app, name="install")

def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"trans2md {__version__}")
        raise typer.Exit()

@app.callback()
def callback(
    version: bool = typer.Option(  # noqa: B008
        False,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="显示版本并退出。",
    ),
) -> None:
    return


def _build_jobs(paths: list[Path]) -> list[LocalFileJob]:
    jobs: list[LocalFileJob] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise typer.BadParameter(f"文件不存在：{resolved}")
        if not resolved.is_file():
            raise typer.BadParameter(f"不是文件：{resolved}")
        jobs.append(
            LocalFileJob(
                source_path=resolved,
                data_id=f"job-{uuid.uuid4().hex}",
            )
        )
    return jobs


def _index_results(results: list[BatchFileResult]) -> dict[str, BatchFileResult]:
    indexed: dict[str, BatchFileResult] = {}
    for result in results:
        if result.data_id:
            indexed[result.data_id] = result
    return indexed


@app.command("convert")
def convert(
    paths: Annotated[
        list[Path],
        typer.Argument(exists=False, readable=True, help="要转换的本地文件"),
    ],
    token: str = typer.Option(
        "",
        "--token",
        envvar="MINERU_API_TOKEN",
        help="MinerU API Token。默认读取环境变量 MINERU_API_TOKEN。",
    ),
    layout: str = typer.Option(
        "auto",
        "--layout",
        help="输出布局：auto（默认）或 bundle。",
    ),
    model_version: str = typer.Option(
        "pipeline",
        "--model-version",
        help="MinerU 模型版本：pipeline、vlm、MinerU-HTML。",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="额外导出一个 JSON 文件，默认选择 content_list.json。",
    ),
    keep_zip: bool = typer.Option(
        False,
        "--keep-zip",
        help="保留 MinerU 返回的原始 ZIP。",
    ),
    language: str = typer.Option(
        "ch",
        "--language",
        help="文档语言，默认 ch。",
    ),
    enable_formula: bool = typer.Option(
        True,
        "--enable-formula/--disable-formula",
        help="是否开启公式识别。",
    ),
    enable_table: bool = typer.Option(
        True,
        "--enable-table/--disable-table",
        help="是否开启表格识别。",
    ),
    is_ocr: bool = typer.Option(
        False,
        "--ocr/--no-ocr",
        help="是否开启 OCR。",
    ),
    poll_interval: float = typer.Option(
        5.0,
        "--poll-interval",
        min=1.0,
        help="结果轮询间隔，单位秒。",
    ),
    timeout: int = typer.Option(
        1800,
        "--timeout",
        min=30,
        help="单次批量任务最长等待时间，单位秒。",
    ),
    request_timeout: int = typer.Option(
        120,
        "--request-timeout",
        min=10,
        help="单次 HTTP 请求超时，单位秒。",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="允许覆盖已有输出文件。",
    ),
) -> None:
    """把本地文件转换为 Markdown。"""
    if not token:
        config = load_config()
        token = config.mineru_api_token or ""
    if not token:
        raise typer.BadParameter(
            "缺少 Token，请传 --token / 设置 MINERU_API_TOKEN / 或运行 trans2md auth set-token"
        )

    jobs = _build_jobs(paths)
    client = MineruClient(token=token, timeout=request_timeout)
    writer = ArtifactWriter(
        keep_zip=keep_zip,
        export_json=json_output,
        overwrite=overwrite,
        layout=layout,
    )

    typer.echo(f"准备上传 {len(jobs)} 个文件...")
    try:
        batch = client.request_upload_urls(
            jobs,
            model_version=model_version,
            language=language,
            enable_formula=enable_formula,
            enable_table=enable_table,
            is_ocr=is_ocr,
        )
        client.upload_files(jobs, batch)
        typer.echo(f"上传完成，batch_id={batch.batch_id}，开始轮询结果...")
        results = client.wait_batch_results(
            batch.batch_id,
            poll_interval=poll_interval,
            deadline_seconds=float(timeout),
        )
        indexed_results = _index_results(results)

        with TemporaryDirectory(prefix="trans2md_zip_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            for job in jobs:
                result = indexed_results.get(job.data_id)
                if result is None:
                    raise MineruApiError(f"未找到文件结果：{job.source_path.name}")
                if result.state == "failed":
                    message = result.err_msg or "MinerU 未返回失败原因"
                    raise MineruApiError(f"{job.source_path.name} 解析失败：{message}")
                if not result.full_zip_url:
                    raise MineruApiError(f"{job.source_path.name} 未返回 full_zip_url")

                temp_zip_path = temp_dir / f"{job.source_path.stem}.zip"
                client.download_zip(result.full_zip_url, temp_zip_path)
                convert_result = writer.materialize(job.source_path, temp_zip_path)

                message = f"完成：{convert_result.markdown_path}"
                if convert_result.image_dir:
                    message += f" | 图片：{convert_result.image_dir}"
                if convert_result.json_path:
                    message += f" | JSON：{convert_result.json_path}"
                if convert_result.zip_path:
                    message += f" | ZIP：{convert_result.zip_path}"
                typer.echo(message)
    except (ArtifactError, MineruApiError, TimeoutError) as exc:
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@auth_app.command("set-token")
def auth_set_token(token: str = typer.Argument(..., help="MinerU API Token")) -> None:
    path = save_token(token)
    typer.echo(f"已写入：{path}")


@auth_app.command("unset-token")
def auth_unset_token() -> None:
    path = clear_token()
    typer.echo(f"已清除：{path}")


@auth_app.command("show")
def auth_show() -> None:
    config = load_config()
    if config.mineru_api_token:
        typer.echo("已配置 MinerU token（存储在本地配置文件中）")
    else:
        typer.echo("未配置 MinerU token")


@install_app.command("codex")
def install_codex(
    overwrite: Annotated[bool, typer.Option("--overwrite", help="覆盖已有 skill")] = False,
) -> None:
    home = Path.home()
    targets = default_targets(home)
    dest = copy_skill_bundle("trans2md", targets.codex_user_skills, overwrite=overwrite)
    record_skill_install("codex", dest)
    typer.echo(f"已安装到 Codex skills：{dest}")


@install_app.command("claude")
def install_claude(
    overwrite: Annotated[bool, typer.Option("--overwrite", help="覆盖已有 skill")] = False,
) -> None:
    home = Path.home()
    targets = default_targets(home)
    dest = copy_skill_bundle("trans2md", targets.claude_user_skills, overwrite=overwrite)
    record_skill_install("claude", dest)
    typer.echo(f"已安装到 Claude Code skills：{dest}")


@install_app.command("openclaw")
def install_openclaw(
    overwrite: Annotated[bool, typer.Option("--overwrite", help="覆盖已有 skill")] = False,
    workspace: Annotated[
        Path | None,
        typer.Option("--workspace", help="安装到指定 workspace 的 skills 目录"),
    ] = None,
) -> None:
    if workspace:
        dest_root = workspace.expanduser().resolve() / "skills"
        dest = copy_skill_bundle("trans2md", dest_root, overwrite=overwrite)
        record_skill_install("openclaw", dest)
        typer.echo(f"已安装到 OpenClaw workspace skills：{dest}")
        return

    home = Path.home()
    targets = default_targets(home)
    dest = copy_skill_bundle("trans2md", targets.openclaw_user_skills, overwrite=overwrite)
    record_skill_install("openclaw", dest)
    typer.echo(f"已安装到 OpenClaw skills：{dest}")


@install_app.command("all")
def install_all(
    overwrite: Annotated[bool, typer.Option("--overwrite", help="覆盖已有 skill")] = False,
) -> None:
    install_codex(overwrite=overwrite)
    install_claude(overwrite=overwrite)
    install_openclaw(overwrite=overwrite, workspace=None)


def _candidate_skill_dirs_from_probe() -> list[Path]:
    home = Path.home()
    candidates: list[Path] = []
    for root in codex_skill_root_candidates(home):
        candidates.append(root / "trans2md")
    candidates.append(home / ".claude" / "skills" / "trans2md")
    for root in openclaw_skill_root_candidates(home):
        candidates.append(root / "trans2md")
    return candidates


@app.command("uninstall")
def uninstall(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="不询问确认，直接执行卸载。",
    ),
    self_uninstall: bool = typer.Option(
        True,
        "--self/--no-self",
        help="最后尝试执行 `uv tool uninstall trans2md` 自卸载（默认开启）。",
    ),
) -> None:
    """
    卸载 trans2md：
    1) 删除已安装的 skills（优先按本地配置记录，其次自动探测常见目录）
    2) 清理本地配置（token + 安装记录）
    3) 可选：尝试 `uv tool uninstall trans2md` 自卸载
    """
    config = load_config()

    # 1) skills
    to_remove: list[Path] = []
    if config.installed_skills:
        for paths in config.installed_skills.values():
            for p in paths:
                try:
                    to_remove.append(Path(p).expanduser())
                except (OSError, ValueError):
                    continue
    to_remove.extend(_candidate_skill_dirs_from_probe())

    # de-dup while preserving order
    seen: set[str] = set()
    unique: list[Path] = []
    for p in to_remove:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    existing = [p for p in unique if p.exists()]
    if not yes:
        typer.echo("将执行以下卸载步骤：")
        typer.echo(f"- 删除 skills 目录（如果存在）：{len(existing)} 个")
        typer.echo("- 清理本地配置（token + 安装记录）")
        if self_uninstall:
            typer.echo("- 尝试执行：uv tool uninstall trans2md")
        if not typer.confirm("确认继续？", default=False):
            raise typer.Exit(code=0)

    removed_any = False
    for p in existing:
        try:
            if p.is_dir():
                shutil.rmtree(p)
                removed_any = True
            else:
                p.unlink()
                removed_any = True
        except OSError as exc:
            typer.secho(f"删除失败：{p}（{exc}）", err=True, fg=typer.colors.RED)

    if removed_any:
        typer.echo("已删除已检测到的 skills。")
    else:
        typer.echo("未检测到已安装的 skills（或已被手动删除）。")

    # 2) local config
    clear_all_config()
    typer.echo("已清理本地配置。")

    # 3) uv tool uninstall
    if self_uninstall:
        try:
            proc = subprocess.run(
                ["uv", "tool", "uninstall", "trans2md"],
                check=False,
                text=True,
                capture_output=True,
            )
            if proc.returncode == 0:
                typer.echo("已执行：uv tool uninstall trans2md")
            else:
                message = (proc.stderr or proc.stdout or "").strip()
                if message:
                    typer.secho(message, err=True, fg=typer.colors.RED)
                typer.secho(
                    "执行 `uv tool uninstall trans2md` 失败（可能当前并非通过 uv tool 安装）。",
                    err=True,
                    fg=typer.colors.RED,
                )
        except FileNotFoundError:
            typer.secho("未找到 uv 命令，跳过自卸载。", err=True, fg=typer.colors.RED)


def main() -> None:
    # 兼容 `trans2md /path/to/file.pdf`：自动注入 `convert`
    known = {"convert", "auth", "install", "uninstall"}
    argv = sys.argv
    if len(argv) >= 2 and not argv[1].startswith("-") and argv[1] not in known:
        argv.insert(1, "convert")
    app()


if __name__ == "__main__":
    main()
