import re


def normalize_markdown_assistant(text: str) -> str:
    """
    Normalize inconsistent markdown produced by LLMs so the TUI
    renderer receives predictable formatting.
    """

    if not text:
        return text

    # Convert headings to bold titles
    text = re.sub(r"^\s*#{1,6}\s*(.+)", r"**\1**", text, flags=re.MULTILINE)

    # Convert "**1. Step**" → "1. **Step**"
    text = re.sub(r"\*\*(\d+)\.\s*(.*?)\*\*", r"\1. **\2**", text)

    # Normalize numbered list spacing
    text = re.sub(r"^\s*(\d+)\.\s*", r"\1. ", text, flags=re.MULTILINE)

    # Normalize bullet styles
    text = re.sub(r"^\s*[•*]\s+", "- ", text, flags=re.MULTILINE)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Convert headings (### Title) → **Title**
    text = re.sub(r"^\s*#{1,6}\s*(.+)", r"**\1**", text, flags=re.MULTILINE)

    # Convert numbered lists → bullet lists
    text = re.sub(r"^\s*\d+\.\s+", "- ", text, flags=re.MULTILINE)

    # Convert unusual bullets → "-"
    text = re.sub(r"^\s*[•*]\s+", "- ", text, flags=re.MULTILINE)

    # Ensure bullets have spacing
    text = re.sub(r"^-\s*", "- ", text, flags=re.MULTILINE)

    # Remove duplicate blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize code block markers
    text = re.sub(r"```(\w+)?\s*\n", r"```\1\n", text)

    # Ensure space after headings/bold sections
    text = re.sub(r"\*\*(.+?)\*\*(\S)", r"**\1** \2", text)

    return text


def normalize_markdown_subagent(text: str) -> str:
    """
    Minimal, safe normalization for subagent Markdown output.
    Preserves all structure (headings, lists, code blocks).
    Only fixes blank-line spacing so Rich renders cleanly.
    """

    if not text:
        return ""

    text = text.strip()

    # Ensure a blank line BEFORE headings (but not at start of text)
    text = re.sub(r"(\S)\n(#{1,6}\s)", r"\1\n\n\2", text)

    # Ensure a blank line AFTER headings
    text = re.sub(r"(#{1,6}\s.+)\n(\S)", r"\1\n\n\2", text)

    # Ensure a blank line BEFORE list blocks (when preceded by a paragraph line)
    text = re.sub(r"([^\n])\n(- |\* |\d+\. )", r"\1\n\n\2", text)

    # Collapse 3+ blank lines down to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize opening code fence: collapse extra blank lines right after ```lang
    text = re.sub(r"(```(?:\w+)?)\n{2,}", r"\1\n", text)

    # Normalize closing code fence: no trailing blank lines inside block
    text = re.sub(r"\n{2,}(```)", r"\n\1", text)

    return text
