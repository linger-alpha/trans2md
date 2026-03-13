---
name: trans2md
description: 把本地 PDF/Office 文档转换成 Markdown（可选导出 JSON）。默认布局为 auto：有图片则输出 <stem>_trans2md/<stem>.md + images/，无图片则直接在源文件同目录输出 <stem>.md。
---

# trans2md

## 快速用法

前置条件：你的系统已安装 `trans2md` 命令（例如通过 `uv tool install trans2md`）。

最常用：

```bash
trans2md "/path/to/file.pdf"
```

可选导出：

```bash
trans2md "/path/to/file.pdf" --json
trans2md "/path/to/file.pdf" --keep-zip
```

覆盖已有输出：

```bash
trans2md "/path/to/file.pdf" --overwrite
```

## Token 管理

推荐把 MinerU token 写入 trans2md 的本地配置（跨平台）：

```bash
trans2md auth set-token "你的token"
```

也支持环境变量：`MINERU_API_TOKEN`，以及命令参数 `--token`（优先级最高）。

## 输出说明

默认输出布局为 `auto`（与源文件同目录）：

- 有图片引用时：`<stem>_trans2md/<stem>.md` + `<stem>_trans2md/images/`
- 无图片引用时：直接输出 `<stem>.md`（不创建 `<stem>_trans2md/`）

如果你希望强制“打包目录”输出（每次都创建 `<stem>_trans2md/`），用：

```bash
trans2md "/path/to/file.pdf" --layout bundle
```

注：目前不提供 “inplace” 输出（不在源文件夹原地创建图片目录），避免污染原目录；有图片时统一输出到 `<stem>_trans2md/`。
