import subprocess
import os
import time
import logging

logger = logging.getLogger(__name__)

class DepotDownloader:
    def __init__(self, path="DepotDownloader", base_dest_dir="manifest_downloads"):
        self.path = path
        self.base_dest_dir = base_dest_dir

    def download_manifest(self, app_id, depot_id, manifest_id, username, password=None):
        logger.info(f"\n>>> Starting download for Manifest: {manifest_id}")
        
        # Build the target directory: <appid>/<depotid>/<manifest>/
        dest_dir = os.path.join(self.base_dest_dir, str(app_id), str(depot_id), str(manifest_id))
        
        # Build the DepotDownloader command
        cmd = [
            self.path,
            "-app", str(app_id),
            "-depot", str(depot_id),
            "-manifest", str(manifest_id),
            "-username", username,
            "-dir", dest_dir,
            "-remember-password"  # Saves your password locally for future runs
        ]
        
        if password:
            cmd.extend(["-password", password])

        # Handle dotnet usage or paths with spaces
        if "dotnet" in self.path:
            cmd = self.path.split() + cmd[1:]

        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                # Run DepotDownloader
                subprocess.run(cmd, check=True)
                logger.info(f"Successfully downloaded manifest {manifest_id} to {dest_dir}")
                return True

            except subprocess.CalledProcessError as e:
                logger.warning(f"Attempt {attempt}/{max_retries}: DepotDownloader encountered an error with manifest {manifest_id}: {e}")
                if attempt == max_retries:
                    logger.error(f"Failed to download manifest {manifest_id} after {max_retries} attempts.")
                    return False
                else:
                    logger.info("Retrying in 3 seconds...")
                    time.sleep(3)  # Wait a bit before retrying in case of file locks (e.g., from antivirus)
            except FileNotFoundError:
                logger.error(f"Error: Could not find '{self.path}'. Ensure it is installed and in your PATH.")
                return False
            except Exception as e:
                logger.exception(f"An unexpected error occurred: {e}")
                return False

if __name__ == "__main__":
    # Test execution
    downloader = DepotDownloader()
    downloader.download_manifest(
        app_id="712100", 
        depot_id="814262", 
        manifest_id="7825130406492684645", 
        username="bukowa51"
    )