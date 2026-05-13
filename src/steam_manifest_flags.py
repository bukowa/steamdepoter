"""Steam depot manifest per-file flags (``EDepotFileFlag``).

Values mirror SteamKit ``Resources/SteamLanguage/enums.steamd`` (``enum EDepotFileFlag flags``).
When Valve adds bits, sync from that file or from DepotDownloader / SteamKit releases.

https://github.com/SteamRE/SteamKit/blob/master/Resources/SteamLanguage/enums.steamd
"""

from __future__ import annotations

from enum import IntFlag
from typing import Iterable

__all__ = [
    "EDepotFileFlag",
    "DEPOT_FILE_FLAG_DIRECTORY",
    "is_directory_entry",
    "iter_edepot_file_flags",
    "format_edepot_file_flags",
]


class EDepotFileFlag(IntFlag):
    """Bit flags on each file mapping in a Steam depot manifest (binary + DepotDownloader text)."""

    USER_CONFIG = 1
    VERSIONED_USER_CONFIG = 2
    ENCRYPTED = 4
    READ_ONLY = 8
    HIDDEN = 16
    EXECUTABLE = 32
    DIRECTORY = 64
    CUSTOM_EXECUTABLE = 128
    INSTALL_SCRIPT = 256
    SYMLINK = 512


# Backwards-compatible name used in SQL filters (plain int for SQLAlchemy ``.op('&')``).
DEPOT_FILE_FLAG_DIRECTORY: int = int(EDepotFileFlag.DIRECTORY)


def is_directory_entry(flags: int | None) -> bool:
    """True for manifest rows that represent depot directories (not downloadable files)."""
    return bool((flags or 0) & DEPOT_FILE_FLAG_DIRECTORY)


_KNOWN_EDEPOT_FILE_MASK = 0
for _m in EDepotFileFlag:
    _KNOWN_EDEPOT_FILE_MASK |= int(_m)


def iter_edepot_file_flags(raw: int | None) -> Iterable[EDepotFileFlag]:
    """Yield each *known* flag bit present in *raw* (unknown high bits are ignored)."""
    if not raw:
        return
    combo = EDepotFileFlag(int(raw) & _KNOWN_EDEPOT_FILE_MASK)
    for m in EDepotFileFlag:
        if m in combo:
            yield m


def format_edepot_file_flags(raw: int | None) -> str:
    """Human-readable flag list for logging/UI, e.g. ``'EXECUTABLE|READ_ONLY'``."""
    parts = [m.name for m in iter_edepot_file_flags(raw)]
    return "|".join(parts) if parts else "0"
