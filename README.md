# trans2md

让 MinerU 更易用的跨平台命令行工具（macOS/Windows/Linux）。

它做两件事：
- 把本地文件转换成 Markdown
- 自动把产物落在“源文件同目录”，并且 Markdown 文件名与源文件一致（仅后缀变为 `.md`）

输出规则（默认 `--layout auto`）：
- 无图片引用：直接在源文件同目录生成 `<stem>.md`
- 有图片引用：创建 `<stem>_trans2md/`，输出 `<stem>_trans2md/<stem>.md` + `<stem>_trans2md/images/`（`md + images/` 可直接渲染）

## 安装

安装为系统命令（`trans2md`）：

```bash
# 直接从 GitHub 安装
uv tool install "trans2md @ git+https://github.com/linger-alpha/trans2md.git"

# 确保 uv 的 tools 目录已加入 PATH（通常只需要执行一次）
uv tool update-shell
```

安装 skills（用于 Codex / Claude Code / OpenClaw 的自然语言入口）：

```bash
trans2md install codex
trans2md install claude
trans2md install openclaw
```

其中 `install codex/openclaw` 会探测常见 skills 目录（存在则优先使用），找不到则创建默认目录。

OpenClaw 若要安装到某个 workspace 下：

```bash
trans2md install openclaw --workspace "/path/to/workspace"
```

## 准备

优先推荐使用项目自带的 token 管理（跨平台）：

```bash
trans2md auth set-token "你的 token"
trans2md auth show
```

也可以使用环境变量 `MINERU_API_TOKEN`：

```bash
export MINERU_API_TOKEN="你的 token"
```

Windows PowerShell：

```powershell
$env:MINERU_API_TOKEN="你的 token"
```

## 使用

基础命令行用法（把文件转成 Markdown，产物自动落在源文件同目录）：

```bash
trans2md "/path/to/file.pdf"
```

Skills 用法（自然语言入口，适合 Codex / Claude Code / OpenClaw）：
- 先按上面的命令 `trans2md install codex|claude|openclaw` 安装对应 skill
- 在对应的产品里，把源文件拖入对话框
- 用自然语言让 Agent 转换为 Markdown（Agent 会调用 `trans2md`，并按本项目默认规则落盘）
  例如：将这个文件转化为 markdown

## 说明

- 可选项（进阶用法）：
- `--overwrite`：允许覆盖已有输出
- `--json`：额外导出 JSON（默认选择 `content_list.json`）
- `--keep-zip`：保留 MinerU 返回的原始 ZIP
- `--layout bundle`：强制每次都创建 `<stem>_trans2md/` 输出（即使没有图片）

- 面向开发者：

```bash
git clone https://github.com/linger-alpha/trans2md.git
cd trans2md
uv sync --group dev
uv run pytest
uv run ruff check .
```
