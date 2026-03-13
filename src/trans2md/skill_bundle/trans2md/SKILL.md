---
name: trans2md
description: 把本地文件转换成 Markdown（可选导出 JSON）
---

# trans2md

## 快速用法

核心原则：对源文件运行 `trans2md`，不要把文件复制到工作区再转换。

最常用：

```bash
trans2md "/path/to/file.pdf"
```
当命令较为简单时（比如将文件转换为 md ）且只有一个文件时，直接运行上述命令，无需了解命令行参数与审查输出结果

支持的文件类型（常用）：

- `.pdf`
- `.doc` / `.docx`
- `.ppt` / `.pptx`
- `.png`
- `.jpg` / `.jpeg`
- `.html`

说明：

- 对图片类文件（`.png/.jpg/.jpeg`）如果你希望识别文字，通常需要加 `--ocr`。
- 路径里有空格/中文时，请务必用引号把路径包起来。

可选导出：

```bash
trans2md "/path/to/file.pdf" --json
trans2md "/path/to/file.pdf" --keep-zip
```

覆盖已有输出：

```bash
trans2md "/path/to/file.pdf" --overwrite
```

## 输出说明

默认输出布局为 `auto`（与源文件同目录）：

- 有图片引用时：`<stem>_trans2md/<stem>.md` + `<stem>_trans2md/images/`
- 无图片引用时：直接输出 `<stem>.md`（不创建 `<stem>_trans2md/`）

如果你希望强制“打包目录”输出（每次都创建 `<stem>_trans2md/`），用：

```bash
trans2md "/path/to/file.pdf" --layout bundle
```
