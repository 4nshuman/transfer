"""Cross-platform path resolution for Copilot artifact stores.

macOS verified empirically; Windows/Linux paths follow the documented VS Code
layout (only the product base dir changes per OS). Add VS Code-family editors
here and every parser picks them up.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# VS Code and forks that reuse its workspaceStorage/chatSessions layout.
VSCODE_FAMILY = [
    "Code",
    "Code - Insiders",
    "VSCodium",
    "Cursor",
    "Windsurf",
]


def _user_data_roots() -> list[Path]:
    """Base dir that contains each editor's `<Product>/User/` tree."""
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support"]
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        return [Path(appdata)] if appdata else [home / "AppData" / "Roaming"]
    # Linux / other POSIX
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return [Path(xdg)] if xdg else [home / ".config"]


def vscode_product_dirs() -> list[tuple[str, Path]]:
    """(editorName, productDir) for every installed VS Code-family editor."""
    out: list[tuple[str, Path]] = []
    for base in _user_data_roots():
        for name in VSCODE_FAMILY:
            d = base / name
            if (d / "User" / "workspaceStorage").is_dir():
                out.append((name, d))
    return out


def vscode_log_dirs() -> list[tuple[str, Path]]:
    """(editorName, logsDir) — plaintext exthost logs incl. Copilot Chat.log."""
    out: list[tuple[str, Path]] = []
    for base in _user_data_roots():
        for name in VSCODE_FAMILY:
            d = base / name / "logs"
            if d.is_dir():
                out.append((name, d))
    return out


def copilot_cli_home() -> Path:
    """Standalone Copilot CLI home (~/.copilot, overridable by COPILOT_HOME)."""
    env = os.environ.get("COPILOT_HOME")
    return Path(env) if env else Path.home() / ".copilot"
