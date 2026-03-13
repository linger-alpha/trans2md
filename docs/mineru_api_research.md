# MinerU API 调研与跨平台技术路线（trans2md）

- 调研时间：2026-03-05
- 调研目标：基于 MinerU 平台实现文件转 Markdown/JSON，并评估 `requests` 直调与 KIE SDK 的差异，给出 macOS/Windows/Linux 可落地方案。

---

## 1. 官方入口与文档映射

你给的入口：

- `https://mineru.net/apiManage/docs`
- `https://mineru.net/apiManage/kie-sdk`

实际内容由文档页承载（可直接检索与引用）：

- 通用解析 API 文档：`https://mineru.net/doc/docs/`
- 限流策略：`https://mineru.net/doc/docs/limit/`
- KIE SDK 文档：`https://mineru.net/doc/docs/kie/`
- KIE 使用说明：`https://mineru.net/doc/docs/kie_usage/`
- 结果文件结构说明：`https://opendatalab.github.io/MinerU/reference/output_files/`

---

## 2. 通用解析 API（适合“文件转 md/json”）

### 2.1 核心接口链路

1. 单文件 URL 解析
- `POST /api/v4/extract/task`
- 入参核心：`url`、`model_version`（`pipeline|vlm|MinerU-HTML`）
- 返回：`task_id`

2. 单任务结果查询
- `GET /api/v4/extract/task/{task_id}`
- 关注状态：`pending` / `running` / `converting` / `done` / `failed`
- 完成后拿 `full_zip_url`

3. 本地文件上传解析（关键）
- `POST /api/v4/file-urls/batch` 先申请上传链接（返回 `batch_id` + `file_urls`）
- 对返回的每个 `file_url` 执行 `PUT` 上传二进制文件
- 上传完成后系统自动提交解析任务（无需再调提交接口）
- 用 `GET /api/v4/extract-results/batch/{batch_id}` 轮询结果

4. URL 批量解析
- `POST /api/v4/extract/task/batch`
- 返回 `batch_id`
- 用 `GET /api/v4/extract-results/batch/{batch_id}` 查询

### 2.2 输出格式与结果文件

- `markdown`、`json` 是默认导出格式（无需额外配置）
- 可选 `extra_formats`: `docx/html/latex`
- 完成后通过 `full_zip_url` 下载压缩包
- 压缩包中可用于二次处理的关键结构（见官方 output_files 文档）：
  - 主 markdown 文件
  - `*_model.json`
  - `*_middle.json`
  - `*_content_list.json`
  - 调试类文件（如 `*_layout.pdf`、`*_span.pdf`，视模式而定）

### 2.3 约束与工程影响

- 单文件：最大 200MB，最多 600 页
- `extract/task` 不支持直接上传本地文件（必须 URL）
- 本地文件应走 `file-urls/batch + PUT`
- 限流（最新文档）：
  - 提交任务类接口共用频控：300 次/分钟
  - 获取结果类接口共用频控：1000 次/分钟
  - 单用户单日上传上限：10000 文件（其中 html 最多 100）
- 回调机制可选：`callback + seed`，带 `checksum` 校验，可减少轮询压力

---

## 3. KIE SDK（`mineru-kie-sdk`）定位

### 3.1 SDK 能力（官方文档）

- 安装：`pip install mineru-kie-sdk`
- 核心类：`MineruKIEClient(base_url="https://mineru.net/api/kie", pipeline_id=...)`
- 核心方法：
  - `upload_file(file_path)`
  - `get_result(file_ids, timeout=60, poll_interval=5)`
- 支持格式：PDF/JPEG/PNG
- 当前版本文档写明：主要是同步轮询模型（异步计划后续）

### 3.2 KIE 场景限制（文档与 FAQ）

- 属于“文档智能抽取”流水线（parse/split/extract）场景
- 依赖 `pipeline_id`（需要先在平台配置并部署流程）
- 文档中出现的典型限制：单文件大小、页数、pipeline 文件数量上限等

---

## 4. `requests` 直调 vs KIE SDK 对比结论

### 4.1 业务适配结论（先给结论）

你的目标是“通用文件转 md/json”。

- 主路径建议：**通用解析 API（`/api/v4/...`）+ 自己封装客户端**
- KIE SDK 作为可选扩展：**面向票据/表单等字段抽取工作流**，不应作为 trans2md 主入口

### 4.2 差异清单

1. 覆盖范围
- `requests`：覆盖完整 `/api/v4` 解析能力（URL单文件、本地上传、批量、回调）
- KIE SDK：覆盖 KIE pipeline 场景，范围更窄

2. 输入文件类型
- `requests` 通用解析：pdf/doc/docx/ppt/pptx/png/jpg/jpeg/html（见官方参数说明）
- KIE SDK：PDF/JPEG/PNG

3. 输出目标
- `requests` 通用解析：默认 md/json（符合 trans2md）
- KIE SDK：parse/split/extract 结构化结果（偏业务抽取）

4. 平台依赖
- `requests`：只依赖 token 与 API
- KIE SDK：依赖 pipeline 配置、部署状态、pipeline_id 生命周期

5. 可控性
- `requests`：你可以完整控制重试、并发、回调验签、落盘规范
- KIE SDK：开发快，但抽象层固定，通用转换定制空间较小

6. 后续演进
- `requests`：最适合做统一“provider”抽象，可扩展到其他解析服务
- KIE SDK：适合作为 `provider_kie` 插件能力

---

## 5. 跨平台技术路线（macOS + Windows + Linux）

### 5.1 推荐总方案（无前端优先）

采用 **Python 核心 + CLI 优先 + 可选轻 UI**：

- 核心语言：Python 3.11+
- 命令行：Typer（或 Click）
- 网络层：`httpx`（同步/异步统一）或 `requests`（简单直接）
- 数据模型：Pydantic
- 本地状态：SQLite（任务队列、去重、重试、审计）
- 打包：
  - 先发 Python 包（`pipx` 安装）
  - 再做单文件打包（PyInstaller）覆盖 Win/mac/Linux

### 5.2 模块拆分建议

1. `provider/mineru_v4.py`
- 封装 `/api/v4` 全链路
- 提供统一接口：`submit_url`、`submit_local_files`、`poll`、`download_zip`

2. `provider/mineru_kie.py`（可选）
- 封装 `mineru-kie-sdk`
- 只用于 KIE 抽取任务

3. `engine/tasks.py`
- 并发调度、指数退避、失败重试、限流令牌桶

4. `engine/artifacts.py`
- ZIP 下载、解压、目标文件提取（md/json）、目录归档

5. `cli/main.py`
- `trans2md run ...`
- `trans2md status ...`
- `trans2md retry ...`

6. `storage/repo.py`
- SQLite 持久化：任务状态、trace_id、错误码、重试次数、输出路径

### 5.3 目录与产物规范（建议）

```text
trans2md/
  input/
  output/
    <job_id>/
      raw.zip
      extracted/
      markdown/
      json/
  logs/
  trans2md.db
```

### 5.4 跨平台关键点

- 路径统一用 `pathlib`
- 网络超时、重试、代理配置可参数化
- 二进制上传时遵循官方说明（PUT 上传不强制 `Content-Type`）
- 轮询频率遵守限流（默认 3~5 秒 + 抖动）
- 对 `full_zip_url` 做过期处理（文档提示文件有效期存在限制）

---

## 6. 实施阶段建议

1. Phase 1（MVP，1-2 天）
- 仅做 `/api/v4/file-urls/batch` 本地上传链路
- 支持单文件/批量文件 -> 输出 md/json 落盘

2. Phase 2（工程化，2-4 天）
- SQLite 任务队列、断点续跑、失败重试、日志审计
- 补齐 URL 提交与 callback 模式

3. Phase 3（产品化，按需）
- 加一个本地 Web UI（FastAPI + 简单前端）或桌面壳（Tauri）
- 支持多 provider（MinerU 通用 API / KIE）

---

## 7. 风险与规避

- 文档/返回结构迭代：接口外层做 schema 兼容与版本检测
- 限流触发：实现全局令牌桶 + 指数退避
- 文件过期：下载环节前置校验并尽快落盘归档
- KIE 资源依赖：pipeline 状态检查前置，不阻塞通用转换主链路

---

## 8. 最终建议

- 你的 trans2md 项目应优先走 **`/api/v4` 通用解析 API**，这是和“转 md/json”目标最匹配、跨平台最好控的路线。
- KIE SDK 作为第二能力面，用于票据/表单字段抽取，不建议替代主链路。
