import os
import re
import sys
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any
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
            
            command = [str(self.binary_path)]

            if self.username:
                command.extend(["-username", self.username])

            if self.password:
                command.extend(["-password", self.password, "-remember-password"])

            command.extend([
                "-app", str(app_id),
                "-manifest-only",
                "-dir", str(app_data_path),
                "-depot", str(depot_id),
                "-manifest", str(manifest_id)
            ])

            sensitive_values = []
            if self.password:
                sensitive_values.append(self.password)

            output = self.runner.run(
                command,
                sensitive_values=sensitive_values,
                on_output=on_output
            )
            
            combined_output += output.stdout + "\n"

            # Parse status from output
            status = MANIFEST_STATUS_ERR_UNKNOWN
            is_ratelimit = False
            
            if "RateLimitExceeded" in output.stdout:
                status = MANIFEST_STATUS_ERR_RATELIMIT
                is_ratelimit = True
            elif re.search(rf"Already have manifest {manifest_id}", output.stdout) or \
               re.search(rf"Got manifest request code.*manifest {manifest_id}", output.stdout):
                status = MANIFEST_STATUS_SUCCESS
            elif re.search(rf"Encountered 401.*{manifest_id}", output.stdout):
                status = MANIFEST_STATUS_ERR_401
            elif re.search(rf"Depot {depot_id} is not available from this account", output.stdout):
                status = MANIFEST_STATUS_ERR_401
                forbidden_depots.add(depot_id)
            elif re.search(rf"Unable to download manifest {manifest_id}", output.stdout):
                if "401" in output.stdout:
                    status = MANIFEST_STATUS_ERR_401
                else:
                    status = MANIFEST_STATUS_ERR_UNKNOWN
            elif output.success:
                status = MANIFEST_STATUS_SUCCESS
            
            # Incremental parsing
            parsed_manifest = None
            manifest_file = self.get_manifest_file_path(app_id, depot_id, manifest_id)
            if manifest_file.exists():
                parsed_manifest = self._parse_manifest_file(manifest_file)
                if parsed_manifest:
                    status = MANIFEST_STATUS_SUCCESS
                    manifests[manifest_id] = parsed_manifest

            statuses[manifest_id] = status
            
            if on_manifest_complete:
                on_manifest_complete(manifest_id, status, parsed_manifest)

            if is_ratelimit:
                logger.error("Rate limit exceeded. Stopping further requests.")
                success = False
                break

            if not output.success and status != MANIFEST_STATUS_SUCCESS:
                logger.error(f"Command failed with code {output.exit_code} for depot {depot_id} manifest {manifest_id}")
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
