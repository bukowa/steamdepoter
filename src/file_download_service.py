import hashlib
from pathlib import Path
from typing import List, Callable, Optional, Dict

from sqlalchemy.orm import Session

from src.db.schema import ManifestFile
from src.bins.depotdownloader import DepotDownloader, DepotFileDownloadEntry, BinOutput
from src.logger import logger

FILE_DL_NONE = 0
FILE_DL_DOWNLOADED = 1
FILE_DL_VERIFIED = 2
FILE_DL_STALE = 3

class FileDownloadService:
    """Orchestrates depot file downloads with skip/verify logic."""

    def __init__(self, session: Session, downloader: DepotDownloader):
        self.session = session
        self.downloader = downloader

    @staticmethod
    def get_download_dir(app_id: int, depot_id: int, manifest_id: int) -> Path:
        """Return the canonical download directory for a manifest."""
        return Path("data/depotdownloader/downloads") / str(app_id) / str(depot_id) / str(manifest_id)

    def download_files_for_manifest(
        self,
        app_id: int,
        depot_id: int,
        manifest_id: int,
        file_rows: List[ManifestFile],
        output_dir: Path,
        *,
        skip_existing: bool = True,
        validate: bool = False,
        on_output: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> BinOutput:
        """
        Download specific files from a manifest and update DB state.
        """
        entries = []
        for file in file_rows:
            entries.append(DepotFileDownloadEntry(
                relative_path=file.name,
                size_bytes=int(file.size) if file.size is not None else 0,
                sha_hex=(file.sha or "").strip()
            ))

        output = self.downloader.download_depot_files(
            app_id=app_id,
            depot_id=depot_id,
            manifest_id=manifest_id,
            entries=entries,
            output_dir=output_dir,
            skip_existing=skip_existing,
            validate_downloaded=validate,
            on_output=on_output,
            is_cancelled=is_cancelled
        )

        if output.success and not (is_cancelled and is_cancelled()):
            # Update local state
            for file in file_rows:
                local_file = output_dir / file.name.replace("\\", "/").strip().lstrip("./")
                file.local_path = str(local_file.resolve())
                
                # Check basic existence / size to tentatively set to DOWNLOADED
                # We do not strictly verify SHA-1 here unless we want to do it immediately, 
                # but validate_downloaded from DepotDownloader checks it.
                if local_file.exists():
                    # If we used validate_downloaded=True, we might consider it FILE_DL_VERIFIED,
                    # but to be safe and separate concerns, let's mark DOWNLOADED and let user verify later.
                    file.download_status = FILE_DL_DOWNLOADED
                else:
                    file.download_status = FILE_DL_STALE

            self.session.commit()

        return output

    def verify_files(self, file_rows: List[ManifestFile]) -> Dict[int, int]:
        """
        Re-check SHA-1 for downloaded files against the DB.
        Returns a dict of {ManifestFile.id: new_status}.
        """
        results = {}
        for file in file_rows:
            if not file.local_path:
                file.download_status = FILE_DL_NONE
                results[file.id] = FILE_DL_NONE
                continue

            local_file = Path(file.local_path)
            if not local_file.exists() or not local_file.is_file():
                file.download_status = FILE_DL_STALE
                results[file.id] = FILE_DL_STALE
                continue

            expected_sha = (file.sha or "").strip().lower()
            if not expected_sha or len(expected_sha) != 40:
                # Can't verify without SHA, but it exists
                file.download_status = FILE_DL_DOWNLOADED
                results[file.id] = FILE_DL_DOWNLOADED
                continue

            # Calculate SHA
            try:
                h = hashlib.sha1()
                with local_file.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                
                if h.hexdigest() == expected_sha:
                    file.download_status = FILE_DL_VERIFIED
                    results[file.id] = FILE_DL_VERIFIED
                else:
                    file.download_status = FILE_DL_STALE
                    results[file.id] = FILE_DL_STALE
            except OSError as e:
                logger.error(f"Error verifying file {file.name}: {e}")
                file.download_status = FILE_DL_STALE
                results[file.id] = FILE_DL_STALE

        self.session.commit()
        return results

    @classmethod
    def execute_download_worker_task(
        cls,
        db_path: str,
        app_id: int,
        depot_id: int,
        manifest_id: int,
        file_names: List[str],
        on_output: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> BinOutput:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        engine = create_engine(f"sqlite:///{db_path}")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            file_rows = session.query(ManifestFile).filter(
                ManifestFile.manifest_id == str(manifest_id),
                ManifestFile.name.in_(file_names)
            ).all()

            downloader = DepotDownloader()
            service = cls(session, downloader)
            output_dir = service.get_download_dir(app_id, depot_id, manifest_id)
            
            return service.download_files_for_manifest(
                app_id=app_id,
                depot_id=depot_id,
                manifest_id=manifest_id,
                file_rows=file_rows,
                output_dir=output_dir,
                skip_existing=True,
                validate=False,
                on_output=on_output,
                is_cancelled=is_cancelled
            )
        finally:
            session.close()
            engine.dispose()

    @classmethod
    def execute_verify_worker_task(
        cls,
        db_path: str,
        manifest_id: int,
        file_names: List[str],
        on_output: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Dict[int, int]:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        engine = create_engine(f"sqlite:///{db_path}")
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        try:
            file_rows = session.query(ManifestFile).filter(
                ManifestFile.manifest_id == str(manifest_id),
                ManifestFile.name.in_(file_names)
            ).all()

            # We pass None for downloader since verify doesn't use it
            service = cls(session, None)
            
            if on_output:
                on_output(f"Verifying {len(file_rows)} files...\n")
                
            results = service.verify_files(file_rows)
            
            if on_output:
                on_output("Verification complete.\n")
                
            return results
        finally:
            session.close()
            engine.dispose()
