#!/usr/bin/env python3
"""Rebuild ## 来源 / ## Sources sections using exact source names from frontmatter.

Reads each wiki page's YAML frontmatter `sources:` list and replaces the
## 来源 section with [[sources/xxx|display_name]] wikilinks.
Requires pyyaml: pip install pyyaml  (or use ~/.venvs/paddleocr/bin/python)
"""
import argparse
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not found. Run: pip install pyyaml")
    raise

SKIP_FILES = {"log.md", "CLAUDE.md", "index.md", "pipeline_report.md"}
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
SOURCES_SECTION_RE = re.compile(r"\n## (?:来源|Sources)\n\n(?:.*\n)*?(?=\n##|\Z)", re.MULTILINE)


def display_name(src: str) -> str:
    return src.split("__")[-1].strip()


def rebuild(wiki_dir: Path) -> tuple[int, int]:
    sources_dir = wiki_dir / "sources"
    if not sources_dir.exists():
        print(f"WARNING: {sources_dir} not found — sources/ must be inside the wiki dir")
        return 0, 0

    valid = {p.name for p in sources_dir.iterdir() if p.is_dir()}
    modified = missing = 0

    for md in wiki_dir.rglob("*.md"):
        if md.name in SKIP_FILES:
            continue
        text = md.read_text(encoding="utf-8")
        fm_match = FRONTMATTER_RE.match(text)
        if not fm_match:
            continue
        try:
            fm = yaml.safe_load(fm_match.group(1))
        except Exception:
            continue

        sources = fm.get("sources", [])
        if not sources:
            continue

        lines = []
        for src in sources:
            if src in valid:
                lines.append(f"- [[sources/{src}|{display_name(src)}]]")
            else:
                lines.append(f"- {src}")
                missing += 1

        header = "\n## 来源\n\n" if "\n## 来源\n" in text else "\n## Sources\n\n"
        new_section = header + "\n".join(lines) + "\n"

        if "\n## 来源\n" in text or "\n## Sources\n" in text:
            new_text = SOURCES_SECTION_RE.sub(new_section, text)
            if new_text == text:
                idx = max(text.rfind("\n## 来源\n"), text.rfind("\n## Sources\n"))
                new_text = text[:idx] + new_section
        else:
            new_text = text.rstrip() + "\n" + new_section

        if new_text != text:
            md.write_text(new_text, encoding="utf-8")
            modified += 1

    return modified, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wiki-dir", required=True)
    args = ap.parse_args()

    wiki_dir = Path(args.wiki_dir).resolve()
    modified, missing = rebuild(wiki_dir)
    print(f"Updated {modified} files, {missing} unresolved source names")


if __name__ == "__main__":
    main()
