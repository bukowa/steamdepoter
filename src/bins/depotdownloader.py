import os
import re
import sys
import json
import tempfile
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from src.logger import logger
from src.errors.errors import SubprocessError, RateLimitError
from src.bins.runner import CommandRunner, BinOutput
from src.settings import Configurable, settings

MANIFEST_STATUS_PENDING = 0
MANIFEST_STATUS_SUCCESS = 1
MANIFEST_STATUS_ERR_401 = 2
MANIFEST_STATUS_ERR_UNKNOWN = 3
MANIFEST_STATUS_ERR_RATELIMIT = 4

@dataclass
class ParsedFile:
    """A single file entry parsed from a DepotDownloader manifest text file."""
    name: str
    size: int
    chunks: int
    sha: str
    flags: int

@dataclass
class ParsedManifest:
    """Manifest metadata + file list parsed from a DepotDownloader manifest text file."""
    depot_id: int
    manifest_id: int
    date: str
    total_files: int
    total_chunks: int
    total_bytes_on_disk: int
    total_bytes_compressed: int
    files: List[ParsedFile]

@dataclass
class ManifestDataOutput(BinOutput):
    """Output of a manifest-data fetch: paths + parsed manifest objects."""
    manifest_path: Path
    manifests: Dict[int, ParsedManifest] = field(default_factory=dict)
    statuses: Dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class DepotFileDownloadEntry:
    """One depot file to fetch: POSIX path as in manifest + size for skip-existing checks."""

    relative_path: str
    size_bytes: int = 0


class DepotDownloader(Configurable):
    """
    A wrapper for the DepotDownloader binary to interact with Steam depots.
    """

    @classmethod
    def get_setting_keys(cls) -> Dict[str, Any]:
        return {
            "username": "",
            "password": ""
        }

    def __init__(
        self,
        binary_path: Optional[str] = None,
        data_path: Optional[str] = None,
        debug: bool = False,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        if not binary_path:
            binary_name = "DepotDownloader.exe" if sys.platform == "win32" else "DepotDownloader"
            binary_path = Path.cwd() / ".bin" / binary_name

        self.binary_path = Path(binary_path).resolve()
        self.root_data_path = Path(data_path or Path("data/depotdownloader"))
        self.manifests_data_path = self.root_data_path / "manifests"
        self.debug = debug
        
        # Use settings if not provided
        self.username = username or settings.get("DepotDownloader", "username")
        self.password = password or settings.get("DepotDownloader", "password")
        
        self.runner = CommandRunner()

    def _parse_manifest_file(self, file_path: Path) -> Optional[ParsedManifest]:
        """
        Parses a single manifest .txt file.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read manifest file {file_path}: {e}")
            return None

        # Regex patterns for header
        depot_id_match = re.search(r"Content Manifest for Depot (\d+)", content)
        manifest_info_match = re.search(r"Manifest ID / date\s+:\s+(\d+)\s+/\s+(.+)", content)
        total_files_match = re.search(r"Total number of files\s+:\s+(\d+)", content)
        total_chunks_match = re.search(r"Total number of chunks\s+:\s+(\d+)", content)
        total_bytes_on_disk_match = re.search(r"Total bytes on disk\s+:\s+(\d+)", content)
        total_bytes_compressed_match = re.search(r"Total bytes compressed\s+:\s+(\d+)", content)

        if not all([depot_id_match, manifest_info_match]):
            logger.warning(f"Could not parse header of manifest file {file_path}")
            return None

        depot_id = int(depot_id_match.group(1))
        manifest_id = int(manifest_info_match.group(1))
        date = manifest_info_match.group(2).strip()
        total_files = int(total_files_match.group(1)) if total_files_match else 0
        total_chunks = int(total_chunks_match.group(1)) if total_chunks_match else 0
        total_bytes_on_disk = int(total_bytes_on_disk_match.group(1)) if total_bytes_on_disk_match else 0
        total_bytes_compressed = int(total_bytes_compressed_match.group(1)) if total_bytes_compressed_match else 0

        # Parse files table
        files = []
        table_started = False
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if "Size" in line and "File SHA" in line:
                table_started = True
                continue

            if table_started:
                # Format: Size Chunks File SHA Flags Name
                # Example: 1099632 2 aee3f559f7d18c776aa358c58e7e4723da103b6f 0 avcodec-53.dll
                file_match = re.match(r"(\d+)\s+(\d+)\s+([a-f0-9]{40})\s+(\d+)\s+(.+)", line)
                if file_match:
                    files.append(ParsedFile(
                        name=file_match.group(5),
                        size=int(file_match.group(1)),
                        chunks=int(file_match.group(2)),
                        sha=file_match.group(3),
                        flags=int(file_match.group(4)),
                    ))

        return ParsedManifest(
            depot_id=depot_id,
            manifest_id=manifest_id,
            date=date,
            total_files=total_files,
            total_chunks=total_chunks,
            total_bytes_on_disk=total_bytes_on_disk,
            total_bytes_compressed=total_bytes_compressed,
            files=files,
        )

    def get_app_data_path(self, app_id: int) -> Path:
        """Returns the base data path for a specific app."""
        return self.manifests_data_path / str(app_id)

    def get_manifest_file_path(self, app_id: int, depot_id: int, manifest_id: int) -> Path:
        """Returns the expected path for a manifest .txt file."""
        return self.get_app_data_path(app_id) / f"manifest_{depot_id}_{manifest_id}.txt"

    def _run_single_manifest_only(
        self,
        app_id: int,
        depot_id: int,
        manifest_id: int,
        app_data_path: Path,
        on_output: Optional[Callable[[str], None]],
    ) -> BinOutput:
        """One ``-manifest-only`` DepotDownloader invocation (used for preflight per depot)."""
        command = [str(self.binary_path)]
        if self.username:
            command.extend(["-username", self.username])
        if self.password:
            command.extend(["-password", self.password, "-remember-password"])
        command.extend(
            [
                "-app",
                str(app_id),
                "-manifest-only",
                "-dir",
                str(app_data_path),
                "-depot",
                str(depot_id),
                "-manifest",
                str(manifest_id),
            ]
        )
        sensitive_values: List[str] = []
        if self.password:
            sensitive_values.append(self.password)
        return self.runner.run(command, sensitive_values=sensitive_values or None, on_output=on_output)

    def _interpret_manifest_fetch_output(
        self, depot_id: int, manifest_id: int, output: BinOutput
    ) -> Tuple[int, bool, bool]:
        """
        Classify DepotDownloader stdout for a single manifest fetch.

        Returns ``(status, depot_forbidden, rate_limited)``.
        *depot_forbidden* is True when this account cannot use the depot at all
        (``Depot {id} is not available from this account``).

        Order of checks matches :meth:`get_manifest_data` (Steam messages rarely overlap).
        """
        stdout = output.stdout
        if "RateLimitExceeded" in stdout:
            return MANIFEST_STATUS_ERR_RATELIMIT, False, True
        if re.search(rf"Already have manifest {manifest_id}", stdout) or re.search(
            rf"Got manifest request code.*manifest {manifest_id}", stdout
        ):
            return MANIFEST_STATUS_SUCCESS, False, False
        if re.search(rf"Encountered 401.*{manifest_id}", stdout):
            return MANIFEST_STATUS_ERR_401, False, False
        if re.search(rf"Depot {depot_id} is not available from this account", stdout):
            return MANIFEST_STATUS_ERR_401, True, False
        if re.search(rf"Unable to download manifest {manifest_id}", stdout):
            if "401" in stdout:
                return MANIFEST_STATUS_ERR_401, False, False
            return MANIFEST_STATUS_ERR_UNKNOWN, False, False
        if output.success:
            return MANIFEST_STATUS_SUCCESS, False, False
        return MANIFEST_STATUS_ERR_UNKNOWN, False, False

    def _finalize_manifest_status_from_disk(
        self,
        app_id: int,
        depot_id: int,
        manifest_id: int,
        status: int,
    ) -> Tuple[int, Optional[ParsedManifest]]:
        """If a manifest .txt exists, parse it and treat as success when parse succeeds."""
        manifest_file = self.get_manifest_file_path(app_id, depot_id, manifest_id)
        if manifest_file.exists():
            parsed = self._parse_manifest_file(manifest_file)
            if parsed:
                return MANIFEST_STATUS_SUCCESS, parsed
        return status, None

    def get_manifest_data(
        self, 
        app_id: int, 
        targets: List[tuple[int, int]], 
        on_output: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        on_manifest_complete: Optional[Callable[[int, int, Optional[ParsedManifest]], None]] = None
    ) -> ManifestDataOutput:
        logger.info(f"Fetching manifest data for App ID {app_id} with {len(targets)} targets...")
        app_data_path = self.get_app_data_path(app_id)
        app_data_path.mkdir(parents=True, exist_ok=True)

        combined_output = ""
        success = True
        statuses = {}
        manifests = {}
        forbidden_depots = set()

        for depot_id, manifest_id in targets:
            if is_cancelled and is_cancelled():
                logger.info("Cancellation requested, stopping manifest fetch loop.")
                self.runner.stop()
                break

            if depot_id in forbidden_depots:
                logger.info(f"Skipping Depot ID {depot_id}, Manifest ID {manifest_id} as depot is marked unavailable.")
                status = MANIFEST_STATUS_ERR_401
                statuses[manifest_id] = status
                if on_manifest_complete:
                    on_manifest_complete(manifest_id, status, None)
                continue

            logger.info(f"Fetching manifest data for App ID {app_id}, Depot ID {depot_id}, Manifest ID {manifest_id}...")

            output = self._run_single_manifest_only(app_id, depot_id, manifest_id, app_data_path, on_output)
            combined_output += output.stdout + "\n"

            status, depot_forbidden, ratelimit = self._interpret_manifest_fetch_output(
                depot_id, manifest_id, output
            )
            if ratelimit:
                statuses[manifest_id] = MANIFEST_STATUS_ERR_RATELIMIT
                if on_manifest_complete:
                    on_manifest_complete(manifest_id, MANIFEST_STATUS_ERR_RATELIMIT, None)
                logger.error("Rate limit exceeded. Stopping further requests.")
                success = False
                break

            if depot_forbidden:
                forbidden_depots.add(depot_id)

            if depot_forbidden:
                final_st, parsed_manifest = MANIFEST_STATUS_ERR_401, None
            else:
                final_st, parsed_manifest = self._finalize_manifest_status_from_disk(
                    app_id, depot_id, manifest_id, status
                )
                if parsed_manifest:
                    manifests[manifest_id] = parsed_manifest

            statuses[manifest_id] = final_st

            if on_manifest_complete:
                on_manifest_complete(manifest_id, final_st, parsed_manifest)

            if not output.success and final_st != MANIFEST_STATUS_SUCCESS:
                logger.error(
                    f"Command failed with code {output.exit_code} for depot {depot_id} manifest {manifest_id}"
                )
                success = False

        logger.info(f"Commands completed.")
        
        if any(s == MANIFEST_STATUS_ERR_RATELIMIT for s in statuses.values()):
            raise RateLimitError("Steam rate limit exceeded. Please wait before trying again.")
        
        final_output = BinOutput(
            command=["depotdownloader", "(batch)"],
            stdout=combined_output,
            stderr="",
            exit_code=0 if success else 1
        )

        return ManifestDataOutput.from_output(final_output, manifest_path=app_data_path, manifests=manifests, statuses=statuses)

    def get_manifest_data_batch(
        self,
        app_id: int,
        targets: List[tuple[int, int]],
        on_output: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        on_manifest_complete: Optional[Callable[[int, int, Optional[ParsedManifest]], None]] = None,
    ) -> ManifestDataOutput:
        """
        Fetch manifest data using ``-batch``.

        Before the batch call, runs **one** ``-manifest-only`` request per depot (first manifest
        in *targets* order). If Steam reports that the depot is unavailable for this account,
        remaining manifests for that depot are skipped (no batch traffic, no parsing) and get
        ``MANIFEST_STATUS_ERR_401``.
        """
        logger.info(f"Fetching manifest data (batch) for App ID {app_id} with {len(targets)} targets...")
        app_data_path = self.get_app_data_path(app_id)
        app_data_path.mkdir(parents=True, exist_ok=True)

        depots_manifests: Dict[int, List[int]] = {}
        for depot_id, manifest_id in targets:
            depots_manifests.setdefault(depot_id, []).append(manifest_id)

        combined_stdout = ""
        success = True
        statuses: Dict[int, int] = {}
        manifests: Dict[int, ParsedManifest] = {}

        # ── Preflight: one manifest per depot (skip whole depot if account cannot access it)
        batch_after_preflight: Dict[int, List[int]] = {}
        for depot_id, manifest_ids in depots_manifests.items():
            if is_cancelled and is_cancelled():
                logger.info("Cancellation requested, stopping manifest preflight.")
                self.runner.stop()
                success = False
                break

            first_mid = manifest_ids[0]
            probe = self._run_single_manifest_only(app_id, depot_id, first_mid, app_data_path, on_output)
            combined_stdout += probe.stdout

            status, depot_forbidden, ratelimit = self._interpret_manifest_fetch_output(
                depot_id, first_mid, probe
            )
            if ratelimit:
                logger.error("Rate limit exceeded during depot preflight.")
                statuses[first_mid] = MANIFEST_STATUS_ERR_RATELIMIT
                if on_manifest_complete:
                    on_manifest_complete(first_mid, statuses[first_mid], None)
                success = False
                raise RateLimitError("Steam rate limit exceeded. Please wait before trying again.")

            if depot_forbidden:
                logger.info(
                    f"Depot {depot_id} unavailable for this account; skipping {len(manifest_ids)} manifest(s)."
                )
                for mid in manifest_ids:
                    statuses[mid] = MANIFEST_STATUS_ERR_401
                    if on_manifest_complete:
                        on_manifest_complete(mid, MANIFEST_STATUS_ERR_401, None)
                continue

            final_st, parsed = self._finalize_manifest_status_from_disk(app_id, depot_id, first_mid, status)
            statuses[first_mid] = final_st
            if parsed:
                manifests[first_mid] = parsed
            if on_manifest_complete:
                on_manifest_complete(first_mid, final_st, parsed)

            if not probe.success and final_st != MANIFEST_STATUS_SUCCESS:
                logger.error(
                    f"Preflight manifest fetch failed (exit {probe.exit_code}) for depot {depot_id} manifest {first_mid}"
                )
                success = False

            rest = manifest_ids[1:]
            if rest:
                batch_after_preflight[depot_id] = rest

        # ── Batch remaining manifests only (depots that passed preflight and have 2+ manifests)
        if batch_after_preflight and not (is_cancelled and is_cancelled()):
            batch_data = {app_id: batch_after_preflight}
            batch_json = json.dumps(batch_data)

            command = [str(self.binary_path)]
            if self.username:
                command.extend(["-username", self.username])
            if self.password:
                command.extend(["-password", self.password, "-remember-password"])
            command.extend(["-batch", batch_json, "-manifest-only", "-dir", str(app_data_path)])

            sensitive_values: List[str] = []
            if self.password:
                sensitive_values.append(self.password)

            output = self.runner.run(
                command, sensitive_values=sensitive_values or None, on_output=on_output
            )
            combined_stdout += output.stdout

            lines = output.stdout.splitlines()
            current_manifest_id: Optional[int] = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                start_match = re.search(
                    r"Starting download for App: (\d+), Depot: (\d+), Manifest: (\d+)", line
                )
                if start_match:
                    current_manifest_id = int(start_match.group(3))
                    continue

                if current_manifest_id is None:
                    continue

                status = MANIFEST_STATUS_ERR_UNKNOWN

                if "RateLimitExceeded" in line:
                    status = MANIFEST_STATUS_ERR_RATELIMIT
                elif re.search(r"Depot \d+ is not available from this account", line):
                    status = MANIFEST_STATUS_ERR_401
                elif re.search(rf"Already have manifest {current_manifest_id}", line):
                    status = MANIFEST_STATUS_SUCCESS
                elif re.search(rf"Got manifest request code.*manifest {current_manifest_id}", line):
                    status = MANIFEST_STATUS_SUCCESS
                elif "Download failed" in line or "Error downloading" in line:
                    status = MANIFEST_STATUS_ERR_UNKNOWN
                elif output.success:
                    status = MANIFEST_STATUS_SUCCESS

                if status != MANIFEST_STATUS_ERR_UNKNOWN:
                    statuses[current_manifest_id] = status

                    parsed_manifest: Optional[ParsedManifest] = None
                    depot_for_mid: Optional[int] = None
                    for d_id, m_ids in batch_after_preflight.items():
                        if current_manifest_id in m_ids:
                            depot_for_mid = d_id
                            break
                    if depot_for_mid is not None:
                        manifest_file = self.get_manifest_file_path(
                            app_id, depot_for_mid, current_manifest_id
                        )
                        if manifest_file.exists():
                            parsed_manifest = self._parse_manifest_file(manifest_file)
                            if parsed_manifest:
                                manifests[current_manifest_id] = parsed_manifest

                    if on_manifest_complete:
                        on_manifest_complete(current_manifest_id, status, parsed_manifest)

            for depot_id, manifest_ids in batch_after_preflight.items():
                for manifest_id in manifest_ids:
                    if manifest_id not in statuses:
                        manifest_file = self.get_manifest_file_path(app_id, depot_id, manifest_id)
                        if manifest_file.exists():
                            parsed_manifest = self._parse_manifest_file(manifest_file)
                            if parsed_manifest:
                                statuses[manifest_id] = MANIFEST_STATUS_SUCCESS
                                manifests[manifest_id] = parsed_manifest
                                if on_manifest_complete:
                                    on_manifest_complete(
                                        manifest_id, MANIFEST_STATUS_SUCCESS, parsed_manifest
                                    )
                            else:
                                statuses[manifest_id] = MANIFEST_STATUS_ERR_UNKNOWN
                                if on_manifest_complete:
                                    on_manifest_complete(
                                        manifest_id, MANIFEST_STATUS_ERR_UNKNOWN, None
                                    )
                        else:
                            statuses[manifest_id] = MANIFEST_STATUS_ERR_UNKNOWN
                            if on_manifest_complete:
                                on_manifest_complete(manifest_id, MANIFEST_STATUS_ERR_UNKNOWN, None)

            if any(s == MANIFEST_STATUS_ERR_RATELIMIT for s in statuses.values()):
                raise RateLimitError("Steam rate limit exceeded. Please wait before trying again.")

            if not output.success:
                success = False

        logger.info("Batch manifest pipeline completed.")

        final_output = BinOutput(
            command=["depotdownloader", "(batch)"],
            stdout=combined_stdout,
            stderr="",
            exit_code=0 if success else 1,
        )

        return ManifestDataOutput.from_output(
            final_output, manifest_path=app_data_path, manifests=manifests, statuses=statuses
        )

    @staticmethod
    def content_path_under_dir(root: Path, relative_posix: str) -> Path:
        """Join *root* with a manifest-relative path (always ``/`` in Steam manifests)."""
        rel = relative_posix.replace("\\", "/").strip().lstrip("./")
        if not rel:
            return root
        return root.joinpath(*rel.split("/"))

    @staticmethod
    def _file_already_matches_expected(path: Path, expected_size: int) -> bool:
        """Whether we can skip downloading *path* (exists and size matches manifest when known)."""
        if not path.is_file():
            return False
        got = path.stat().st_size
        if expected_size > 0:
            return got == expected_size
        return got == 0

    def filter_entries_missing_on_disk(
        self,
        output_dir: Path,
        entries: List[DepotFileDownloadEntry],
        *,
        skip_existing: bool,
    ) -> List[DepotFileDownloadEntry]:
        """Drop entries that already sit on disk with the expected size (see :meth:`download_depot_files`)."""
        if not skip_existing:
            return list(entries)
        root = Path(output_dir).resolve()
        out: List[DepotFileDownloadEntry] = []
        for e in entries:
            p = self.content_path_under_dir(root, e.relative_path)
            if self._file_already_matches_expected(p, e.size_bytes):
                continue
            out.append(e)
        return out

    def download_depot_files(
        self,
        app_id: int,
        depot_id: int,
        manifest_id: int,
        entries: List[DepotFileDownloadEntry],
        output_dir: Path,
        *,
        skip_existing: bool = True,
        validate_downloaded: bool = False,
        on_output: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> BinOutput:
        """
        Download concrete files for one depot+manifest using DepotDownloader's ``-filelist``.

        The list file is one relative path per line (``\\`` normalized to ``/``); optional
        ``regex:`` lines are supported by DepotDownloader itself — we only emit plain paths here.

        When *skip_existing* is True, paths whose on-disk file already matches *size_bytes*
        from the manifest are omitted (large selections should pass real sizes from the DB).
        Pass ``validate_downloaded=True`` to add ``-validate`` (checksum verification).
        """
        if is_cancelled and is_cancelled():
            return BinOutput(command=[str(self.binary_path)], stdout="", stderr="Cancelled before start.\n", exit_code=1)

        root = Path(output_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)

        todo = self.filter_entries_missing_on_disk(root, entries, skip_existing=skip_existing)
        if not todo:
            return BinOutput(
                command=[str(self.binary_path), "(no run: all files already present)"],
                stdout="All requested files already present on disk; nothing to download.\n",
                stderr="",
                exit_code=0,
            )

        list_path: Optional[Path] = None
        try:
            fd, list_path_str = tempfile.mkstemp(prefix="steamdepoter-filelist-", suffix=".txt", text=True)
            os.close(fd)
            list_path = Path(list_path_str)
            lines = [e.relative_path.replace("\\", "/").strip() for e in todo]
            list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            command = [str(self.binary_path)]
            if self.username:
                command.extend(["-username", self.username])
            if self.password:
                command.extend(["-password", self.password, "-remember-password"])
            command.extend(
                [
                    "-app",
                    str(app_id),
                    "-depot",
                    str(depot_id),
                    "-manifest",
                    str(manifest_id),
                    "-dir",
                    str(root),
                    "-filelist",
                    str(list_path),
                ]
            )
            if validate_downloaded:
                command.append("-validate")

            sensitive_values: List[str] = []
            if self.password:
                sensitive_values.append(self.password)

            return self.runner.run(command, sensitive_values=sensitive_values or None, on_output=on_output)
        finally:
            if list_path is not None:
                try:
                    list_path.unlink(missing_ok=True)
                except TypeError:
                    if list_path.exists():
                        list_path.unlink()
                except OSError:
                    pass
