# trans2md

基于 MinerU 通用解析 API 的 Python CLI。当前 MVP 只做一件事：把本地文件转换成 Markdown，并在有图片时把图片整理到与 Markdown 同级的 `images/` 目录，确保 `md + images/` 足够直接渲染出文档。

## 安装

面向普通用户（安装为系统命令）：

```bash
uv tool install trans2md
```

面向开发者（本仓库内开发）：

```bash
cd /Users/linger/Documents/Python/codex_workplace/trans2md
uv sync --group dev
```

## 准备

设置 MinerU Token：

```bash
export MINERU_API_TOKEN="你的 token"
```

Windows PowerShell：

```powershell
$env:MINERU_API_TOKEN="你的 token"
```

## 用法

默认输出 Markdown：

```bash
trans2md "/path/to/demo.pdf"
```

一次处理多个文件：

```bash
trans2md "/path/to/a.pdf" "/path/to/b.docx"
```

显式调用子命令也可以：

```bash
trans2md convert "/path/to/demo.pdf"
```

需要 JSON 时显式打开。默认导出 `content_list.json`，这是最接近阅读顺序的结构化结果：

```bash
trans2md "/path/to/demo.pdf" --json
```

如果你还想保留 MinerU 返回的原始 ZIP：

```bash
trans2md "/path/to/demo.pdf" --keep-zip
```

## Token 管理

推荐写入本地配置文件（跨平台）：

```bash
trans2md auth set-token "你的 token"
trans2md auth show
```

也支持环境变量：`MINERU_API_TOKEN`，以及 `--token`（优先级最高）。

## 安装 Skills

仿照 helloagents 的方式，使用 CLI 显式安装 skill 到对应产品的目录：

```bash
trans2md install codex
trans2md install claude
trans2md install openclaw
```

其中 `install codex/openclaw` 会探测常见 skills 目录（存在则优先使用），找不到则创建默认目录：
- Codex：优先 `~/.codex/skills/`，若已存在旧目录则用 `~/.agents/skills/`
- OpenClaw：优先 `~/.openclaw/workspace/skills/`（若存在），否则 `~/.openclaw/skills/`

OpenClaw 若要安装到某个 workspace 下：

```bash
trans2md install openclaw --workspace "/path/to/workspace"
```

## 默认产物

默认输出布局为 `auto`（与源文件同目录）：
- 有图片引用时：创建 `demo_trans2md/`，输出 `demo_trans2md/demo.md` + `demo_trans2md/images/`
- 无图片引用时：直接输出 `demo.md`（不额外创建 `demo_trans2md/`）

## 可选产物

- `--json`：额外导出 JSON（有图片时放在 `demo_trans2md/`，无图片时与 `demo.md` 同目录）
- `--keep-zip`：保留 MinerU 返回的原始 ZIP（同上）

## 说明

- `bundle/auto(有图)`：保留 MinerU 的默认相对路径（通常是 `images/...`，与 md 平级）
- 默认不保留调试类 PDF、结构化 JSON、原始 ZIP，避免污染目录
- 如果输出文件已存在，需要显式传 `--overwrite`
- 输出布局默认 `auto`。如需强制打包文件夹输出，用：`--layout bundle`

## 开发命令

```bash
uv run trans2md --help
uv run trans2md --version
uv run pytest
uv run ruff check .
```

如果你在本仓库内开发时遇到 `uv run trans2md` 不可用，可以直接用源码运行：

```bash
PYTHONPATH="src" python -m trans2md --help
```
