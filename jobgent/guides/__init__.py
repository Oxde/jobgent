"""Writing guides the agents follow (also shipped to MCP clients)."""

from pathlib import Path

_DIR = Path(__file__).parent


def cv_writing_guide() -> str:
    return (_DIR / "cv-writing.md").read_text()
