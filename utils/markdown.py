import re


def normalize_markdown(text: str) -> str:
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
