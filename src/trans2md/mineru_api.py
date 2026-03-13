from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from trans2md.models import BatchFileResult, LocalFileJob, UploadBatch


class MineruApiError(RuntimeError):
    """MinerU API 请求失败。"""


class MineruClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://mineru.net/api/v4",
        timeout: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "*/*",
            }
        )

    def request_upload_urls(
        self,
        jobs: list[LocalFileJob],
        *,
        model_version: str,
        language: str | None,
        enable_formula: bool,
        enable_table: bool,
        is_ocr: bool,
    ) -> UploadBatch:
        files: list[dict[str, Any]] = []
        for job in jobs:
            files.append(
                {
                    "name": job.source_path.name,
                    "data_id": job.data_id,
                    "is_ocr": is_ocr,
                }
            )

        payload: dict[str, Any] = {
            "files": files,
            "model_version": model_version,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
        }
        if language:
            payload["language"] = language

        try:
            response = self.session.post(
                f"{self.base_url}/file-urls/batch",
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MineruApiError(f"请求上传链接失败：{exc}") from exc
        data = self._parse_json_response(response)
        batch_id = self._read_str(data, ("data", "batch_id"))
        file_urls = self._read_str_list(data, ("data", "file_urls"))
        if len(file_urls) != len(jobs):
            message = f"上传链接数量异常：期望 {len(jobs)}，实际 {len(file_urls)}"
            raise MineruApiError(message)
        return UploadBatch(batch_id=batch_id, file_urls=file_urls)

    def upload_files(self, jobs: list[LocalFileJob], batch: UploadBatch) -> None:
        for job, upload_url in zip(jobs, batch.file_urls, strict=True):
            with job.source_path.open("rb") as file_handle:
                try:
                    response = self.session.put(upload_url, data=file_handle, timeout=self.timeout)
                except requests.RequestException as exc:
                    # Some environments (notably LibreSSL builds) can hit TLS EOF issues with OSS.
                    # Fall back to system curl for robustness.
                    self._upload_with_curl(upload_url, job.source_path, exc=exc)
                    continue

            if response.status_code != requests.codes.ok:
                # Retry with curl on non-200 as well (OSS presigned URLs can be picky).
                self._upload_with_curl(upload_url, job.source_path)

    def _upload_with_curl(self, url: str, source: Path, *, exc: Exception | None = None) -> None:
        curl_path = shutil.which("curl")
        if not curl_path:
            prefix = f"上传文件失败：{source.name}"
            if exc:
                raise MineruApiError(f"{prefix} -> {exc}") from exc
            raise MineruApiError(f"{prefix}（HTTP 非 200，且当前环境不可用 curl 作为降级方案）")
        try:
            # -T uses PUT by default.
            subprocess.run(
                [
                    curl_path,
                    "-L",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--retry",
                    "3",
                    "--retry-all-errors",
                    "-T",
                    str(source),
                    url,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as curl_exc:
            prefix = f"上传文件失败：{source.name}"
            if exc:
                raise MineruApiError(f"{prefix} -> {exc}（curl 降级也失败：{curl_exc}）") from exc
            raise MineruApiError(f"{prefix}（curl 降级失败：{curl_exc}）") from curl_exc

    def wait_batch_results(
        self,
        batch_id: str,
        *,
        poll_interval: float,
        deadline_seconds: float,
    ) -> list[BatchFileResult]:
        started_at = time.monotonic()
        while True:
            try:
                response = self.session.get(
                    f"{self.base_url}/extract-results/batch/{batch_id}",
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise MineruApiError(f"查询批量结果失败：{exc}") from exc
            data = self._parse_json_response(response)
            results = self._parse_batch_results(data)
            if results and all(item.state in {"done", "failed"} for item in results):
                return results
            if time.monotonic() - started_at > deadline_seconds:
                raise TimeoutError(f"轮询超时：batch_id={batch_id}")
            time.sleep(poll_interval)

    def download_zip(self, url: str, destination: Path) -> Path:
        try:
            response = self.session.get(url, stream=True, timeout=self.timeout)
        except requests.RequestException:
            self._download_with_curl(url, destination)
            return destination
        with response:
            if response.status_code != requests.codes.ok:
                message = f"下载结果 ZIP 失败：HTTP {response.status_code}"
                raise MineruApiError(message)
            with destination.open("wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        file_handle.write(chunk)
        return destination

    def _download_with_curl(self, url: str, destination: Path) -> None:
        curl_path = shutil.which("curl")
        if not curl_path:
            raise MineruApiError("下载结果 ZIP 失败，且当前环境不可用 curl 作为降级方案")
        try:
            subprocess.run(
                [
                    curl_path,
                    "-L",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "-o",
                    str(destination),
                    url,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise MineruApiError(f"下载结果 ZIP 失败，curl 降级也失败：{exc}") from exc

    def _parse_batch_results(self, payload: dict[str, Any]) -> list[BatchFileResult]:
        raw_results = self._read_list(payload, ("data", "extract_result"))
        results: list[BatchFileResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise MineruApiError("批量结果格式异常：extract_result 项不是对象")
            results.append(
                BatchFileResult(
                    file_name=self._read_optional_str(item, "file_name") or "",
                    state=self._read_optional_str(item, "state") or "",
                    err_msg=self._read_optional_str(item, "err_msg") or "",
                    full_zip_url=self._read_optional_str(item, "full_zip_url"),
                    data_id=self._read_optional_str(item, "data_id"),
                )
            )
        return results

    def _parse_json_response(self, response: requests.Response) -> dict[str, Any]:
        if response.status_code != requests.codes.ok:
            message = f"MinerU API 请求失败：HTTP {response.status_code}"
            raise MineruApiError(message)
        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - requests 自身行为
            raise MineruApiError("MinerU API 返回的不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise MineruApiError("MinerU API 返回结构异常")
        if payload.get("code") != 0:
            msg = payload.get("msg", "未知错误")
            raise MineruApiError(f"MinerU API 业务失败：{msg}")
        return payload

    @staticmethod
    def _read_optional_str(data: dict[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        raise MineruApiError(f"字段类型异常：{key}")

    @staticmethod
    def _read_str(data: dict[str, Any], path: tuple[str, ...]) -> str:
        value: Any = data
        for key in path:
            if not isinstance(value, dict) or key not in value:
                raise MineruApiError(f"缺少字段：{'.'.join(path)}")
            value = value[key]
        if not isinstance(value, str):
            raise MineruApiError(f"字段类型异常：{'.'.join(path)}")
        return value

    @staticmethod
    def _read_list(data: dict[str, Any], path: tuple[str, ...]) -> list[Any]:
        value: Any = data
        for key in path:
            if not isinstance(value, dict) or key not in value:
                raise MineruApiError(f"缺少字段：{'.'.join(path)}")
            value = value[key]
        if not isinstance(value, list):
            raise MineruApiError(f"字段类型异常：{'.'.join(path)}")
        return value

    def _read_str_list(self, data: dict[str, Any], path: tuple[str, ...]) -> list[str]:
        values = self._read_list(data, path)
        result: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise MineruApiError(f"字段类型异常：{'.'.join(path)}")
            result.append(value)
        return result
