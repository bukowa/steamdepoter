"""Path hide rules for the Library file pane + manifest DB import.

Each non-empty line is a **Unix-style glob** matched with :class:`pathlib.PurePosixPath`
(``**`` supported), e.g. ``**/*.lua``, ``**/Content/Localization/**``, ``*.md``.
Pure ``**/*.<literal>`` lines (no ``*?[]{}`` in the suffix) are resolved at compile time to a
suffix set so filtering large file lists stays fast.

Lines starting with ``re:`` are **Python regexes** matched against the full
forward-slash path (case-sensitive).

Defaults are generated from **sindresorhus/text-extensions** (MIT) as ``**/*.<ext>``:
https://github.com/sindresorhus/text-extensions

Persistence: ``data/settings.json`` via :class:`src.settings.SettingsManager`
(keys under ``globals``: ``library_hide_patterns``, ``library_hide_patterns_enabled``).
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, List, Optional, Tuple

_TEXT_JSON_PATH = Path(__file__).resolve().parent / "gui" / "data" / "text_extensions.json"

# Whole pattern is ``**/*.<literal>`` with no glob metacharacters in <literal> — matched via suffix sets (O(1)).
_STARSTAR_EXT_LITERAL = re.compile(r"^\*\*/\*\.(.+)$")
_GLOB_METACHAR_IN_LITERAL = frozenset("*?[{\\")

_EXTRA_TEXT_SUFFIXES = frozenset(
    {
        "toml",
        "tf",
        "tfvars",
        "hcl",
        "adoc",
        "asciidoc",
        "kts",
        "containerfile",
        "dockerignore",
    }
)

_hide_filter_enabled: bool = True
_patterns_text: str = ""
# ``**/*.<one_segment_ext>`` e.g. ``lua`` → last path segment ends with ``.lua``
_fast_hide_single_exts: frozenset[str] = frozenset()
# ``**/*.<literal>`` where literal contains ``.`` (e.g. ``tar.gz``) → basename endswith ``.<literal>``
_fast_hide_compound_suffixes: frozenset[str] = frozenset()
_complex_glob_patterns: List[str] = []
_regex_patterns: List[re.Pattern[str]] = []
_last_persisted_text: str = ""
_default_patterns_document_cache: Optional[str] = None


def _normalize_posix_path(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("./")


def _load_bundled_text_suffixes() -> frozenset[str]:
    raw = json.loads(_TEXT_JSON_PATH.read_text(encoding="utf-8"))
    base = frozenset(str(x).lstrip(".").lower() for x in raw)
    return base | _EXTRA_TEXT_SUFFIXES


def default_patterns_document() -> str:
    """Default hide rules: one glob per text-like extension."""
    global _default_patterns_document_cache
    if _default_patterns_document_cache is None:
        parts = [f"**/*.{ext}" for ext in sorted(_load_bundled_text_suffixes())]
        _default_patterns_document_cache = "\n".join(parts)
    return _default_patterns_document_cache


def _literal_for_pure_starstar_ext_glob(normalized_glob: str) -> Optional[str]:
    """
    If *normalized_glob* is only ``**/*.<literal>`` with no glob syntax inside the suffix,
    return that literal (original casing); otherwise None (needs :func:`PurePosixPath.match`).
    """
    m = _STARSTAR_EXT_LITERAL.match(normalized_glob)
    if not m:
        return None
    lit = m.group(1)
    if not lit or any(ch in lit for ch in _GLOB_METACHAR_IN_LITERAL):
        return None
    return lit


def _parse_and_compile(text: str) -> Tuple[frozenset[str], frozenset[str], List[str], List[re.Pattern[str]]]:
    fast_single: set[str] = set()
    fast_compound: set[str] = set()
    complex_globs: List[str] = []
    regexes: List[re.Pattern[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("re:"):
            body = line[3:].strip()
            if not body:
                continue
            try:
                regexes.append(re.compile(body))
            except re.error:
                continue
        else:
            pat = _normalize_posix_path(line)
            lit = _literal_for_pure_starstar_ext_glob(pat)
            if lit is not None:
                low = lit.lower()
                if "." in lit:
                    fast_compound.add(low)
                else:
                    fast_single.add(low)
            else:
                complex_globs.append(pat)
    return frozenset(fast_single), frozenset(fast_compound), complex_globs, regexes


def set_patterns_from_text(text: str) -> None:
    """Update in-memory rules (live preview). Does not write ``settings.json``."""
    global _patterns_text, _fast_hide_single_exts, _fast_hide_compound_suffixes, _complex_glob_patterns, _regex_patterns
    _patterns_text = text
    _fast_hide_single_exts, _fast_hide_compound_suffixes, _complex_glob_patterns, _regex_patterns = _parse_and_compile(
        text
    )


def get_patterns_text() -> str:
    return _patterns_text


def set_hide_filter_enabled(enabled: bool) -> None:
    global _hide_filter_enabled
    _hide_filter_enabled = bool(enabled)


def is_hide_filter_enabled() -> bool:
    return _hide_filter_enabled


# Backwards-compatible names used by older code paths
def set_filter_non_binary_enabled(enabled: bool) -> None:
    set_hide_filter_enabled(enabled)


def is_filter_non_binary_enabled() -> bool:
    return is_hide_filter_enabled()


def init_from_app_settings(settings_manager: Any) -> None:
    """
    Load filter flag + pattern text from ``settings.json``.
    Call after ``QApplication`` exists (migration may run separately).
    """
    global _last_persisted_text
    mgr = settings_manager
    raw_en = mgr.get("globals", "library_hide_patterns_enabled")
    if raw_en is None:
        enabled = True
    elif isinstance(raw_en, str):
        enabled = raw_en.strip().lower() not in ("0", "false", "no", "off")
    else:
        enabled = bool(raw_en)
    set_hide_filter_enabled(enabled)

    raw_txt = mgr.get("globals", "library_hide_patterns")
    if raw_txt is None or not str(raw_txt).strip():
        doc = default_patterns_document()
    else:
        doc = str(raw_txt)
    set_patterns_from_text(doc)
    _last_persisted_text = doc


def persist_patterns_to_disk(settings_manager: Any, text: str) -> None:
    """Write pattern document to ``data/settings.json``."""
    global _last_persisted_text
    settings_manager.set_global("library_hide_patterns", text)
    _last_persisted_text = text


def get_last_persisted_patterns_text() -> str:
    return _last_persisted_text


def patterns_text_is_dirty(current_text: str) -> bool:
    return current_text != _last_persisted_text


def _final_path_segment(norm: str) -> str:
    slash = norm.rfind("/")
    return norm if slash < 0 else norm[slash + 1 :]


def path_matches_hide_rules(relative_path: str) -> bool:
    """True if *relative_path* matches any glob or regex rule."""
    norm = _normalize_posix_path(relative_path)
    if not norm:
        return False
    base = _final_path_segment(norm)
    bl = base.lower()

    if _fast_hide_single_exts:
        dot = base.rfind(".")
        if dot >= 0 and base[dot + 1 :].lower() in _fast_hide_single_exts:
            return True
    if _fast_hide_compound_suffixes:
        for suf in _fast_hide_compound_suffixes:
            if bl.endswith("." + suf):
                return True
    if _complex_glob_patterns:
        pp = PurePosixPath(norm)
        for pat in _complex_glob_patterns:
            try:
                if pp.match(pat):
                    return True
            except ValueError:
                continue
    for rx in _regex_patterns:
        if rx.search(norm):
            return True
    return False


def should_hide_non_binary_path(relative_path: str) -> bool:
    """When the hide filter is on, return True if this path should be removed from view."""
    if not _hide_filter_enabled:
        return False
    return path_matches_hide_rules(relative_path)


def should_skip_manifest_file_import(relative_path: str) -> bool:
    """Same as :func:`should_hide_non_binary_path` (used when saving manifest files)."""
    return should_hide_non_binary_path(relative_path)
