# {COMPANY_NAME} 知识库 — 构建报告

> 生成时间：{DATE}
> 源目录：`{SOURCE_DIR}`

---

## 一、原始文件收集

| 格式 | 数量 | 说明 |
|------|------|------|
| PPTX | N | 演示文稿 |
| PDF  | N | 报告、方案 |
| DOCX | N | 文档 |
| **合计** | **N** | 跳过所有 Excel/CSV |

来源目录：{list top-level subdirectories}

## 二、PDF 转换（LibreOffice）

| 指标 | 数值 |
|------|------|
| 输入文件 | N（PPTX + DOCX + PPSX） |
| 转换成功 | N |
| 转换失败 | N |
| 成功率 | N% |
| 耗时 | Ns（{WORKERS} worker 并行） |

失败原因：{brief summary}

## 三、OCR 提取（PaddleOCR 云端）

| 指标 | 数值 |
|------|------|
| 输入 PDF | N（转换 + 原始 - 重复） |
| OCR 成功 | N |
| OCR 失败 | N |
| 成功率 | N% |
| 产出 MD 文件 | N |
| 产出图片 | N |
| 总大小 | N MB |
| 耗时 | ~N 小时 |

## 四、Wiki 知识库

| 指标 | 数值 |
|------|------|
| 总页面数 | N |
| 总行数 | N |
| 总大小 | N KB |
| 交叉引用 | N [[wikilink]] |

### 页面分布

| 分类 | 页面数 | 代表页面 |
|------|--------|---------|
| solutions | N | ... |
| products  | N | ... |
| clients   | N | ... |
| concepts  | N | ... |

### 源文件覆盖率

- 源文件映射：N/N（N%）
- 跳过（内部/模板）：N
- 未映射：N

## 五、管线工具

| 脚本 | 用途 |
|------|------|
| `01_collect_docs.py` | 收集可转换文档 |
| `02_convert_to_pdf.py` | LibreOffice 并行转 PDF |
| `03_run_ocr.py` | PaddleOCR 批量 OCR |
| `04_run_ocr_remaining.py` | OCR 补跑剩余文件 |
| `05_merge_ocr.py` | 合并 OCR 结果 |
| `06_rebuild_source_links.py` | 重建 wiki 来源 wikilink |

## 六、最终目录结构

```
{WIKI_DIR}/
├── solutions/
├── products/
├── clients/
├── concepts/
├── sources/          ← OCR 输出（N 文档 + N 图片）
├── _sources/         ← source_map.json
├── index.md
├── CLAUDE.md
└── log.md
```
