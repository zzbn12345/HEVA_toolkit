"""Native folder selection for the local HEVA web application."""

from __future__ import annotations

import platform
import shutil
import subprocess


class FolderPickerUnavailable(RuntimeError):
    """Raised when the operating system has no supported folder chooser."""


def select_local_folder(prompt: str) -> str | None:
    """Open the operating system folder chooser and return its selected path.

    HEVA is a local application. A browser directory input cannot disclose an
    absolute path and would upload file copies instead, so the local service
    opens a native chooser without reading or moving the selected folder.
    """

    system = platform.system()
    if system == "Darwin":
        command = [
            "osascript",
            "-e",
            f'POSIX path of (choose folder with prompt "{_apple_script_text(prompt)}")',
        ]
    elif system == "Windows":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$dialog.Description = '{_powershell_text(prompt)}'; "
                "if ($dialog.ShowDialog() -eq 'OK') { $dialog.SelectedPath }"
            ),
        ]
    elif shutil.which("zenity"):
        command = ["zenity", "--file-selection", "--directory", f"--title={prompt}"]
    elif shutil.which("kdialog"):
        command = ["kdialog", "--getexistingdirectory", ".", "--title", prompt]
    else:
        raise FolderPickerUnavailable(
            "No supported system folder chooser is available on this computer."
        )

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    selected = result.stdout.strip()
    return selected or None


def _apple_script_text(value: str) -> str:
    """Escape user-facing text embedded in an AppleScript string."""

    return value.replace("\\", "\\\\").replace('"', '\\"')


def _powershell_text(value: str) -> str:
    """Escape user-facing text embedded in a PowerShell single-quoted string."""

    return value.replace("'", "''")
