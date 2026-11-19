"""Turn the plain-text answers in the knowledge base into Markdown for the web UI."""

from __future__ import annotations


def to_markdown(text: str) -> str:
    """Render titles in bold, product lines as a list and notes in italics.

    The terminal keeps the original plain text; only the web interface uses this.
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if line.startswith("★"):
            out += [f"**{line.strip('★ ').strip()}**", ""]
        elif line.startswith("【"):
            out += ["", f"*{line.strip('【】 ')}*", ""]
        elif line.endswith(":") and not line.startswith("- "):
            out += ["", f"**{line[:-1].strip()}**"]
        elif line.startswith("- "):
            out.append(f"- {line[2:].strip()}")
        elif line[-1] in ".!?":
            out.append(line)
        else:
            out.append(f"- {line}")
    return "\n".join(out).strip()
