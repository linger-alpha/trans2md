from __future__ import annotations

import sys
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

import typer

from trans2md import __version__
from trans2md.artifacts import ArtifactError, ArtifactWriter
from trans2md.config import clear_token, load_config, save_token
from trans2md.installer import copy_skill_bundle, default_targets
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
    typer.echo(f"已安装到 Codex skills：{dest}")


@install_app.command("claude")
def install_claude(
    overwrite: Annotated[bool, typer.Option("--overwrite", help="覆盖已有 skill")] = False,
) -> None:
    home = Path.home()
    targets = default_targets(home)
    dest = copy_skill_bundle("trans2md", targets.claude_user_skills, overwrite=overwrite)
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
        typer.echo(f"已安装到 OpenClaw workspace skills：{dest}")
        return

    home = Path.home()
    targets = default_targets(home)
    dest = copy_skill_bundle("trans2md", targets.openclaw_user_skills, overwrite=overwrite)
    typer.echo(f"已安装到 OpenClaw skills：{dest}")


@install_app.command("all")
def install_all(
    overwrite: Annotated[bool, typer.Option("--overwrite", help="覆盖已有 skill")] = False,
) -> None:
    install_codex(overwrite=overwrite)
    install_claude(overwrite=overwrite)
    install_openclaw(overwrite=overwrite, workspace=None)


def main() -> None:
    # 兼容 `trans2md /path/to/file.pdf`：自动注入 `convert`
    known = {"convert", "auth", "install"}
    argv = sys.argv
    if len(argv) >= 2 and not argv[1].startswith("-") and argv[1] not in known:
        argv.insert(1, "convert")
    app()


if __name__ == "__main__":
    main()
