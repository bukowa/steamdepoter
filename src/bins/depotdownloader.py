import os
import sys
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass

from src.logger import logger
from src.errors.errors import SubprocessError
from src.bins.runner import CommandRunner, BinOutput

@dataclass
class DepotManifestsOutput(BinOutput):
    """
    Specialized output for the get_depots command.
    """
    manifest_path: Path

class DepotDownloader:
    """
    A wrapper for the DepotDownloader binary to interact with Steam depots.
    """

    def __init__(
        self,
        binary_path: Optional[str] = None,
        data_path: Optional[str] = None,
        debug: bool = False,
        username: str = "anonymous",
        password: str = ""
    ):
        if not binary_path:
            binary_name = "DepotDownloader.exe" if sys.platform == "win32" else "DepotDownloader"
            binary_path = Path.cwd() / ".bin" / binary_name

        self.binary_path = Path(binary_path).resolve()
        self.root_data_path = Path(data_path or Path("data/depotdownloader"))
        self.manifests_data_path = self.root_data_path / "manifests"
        self.debug = debug
        self.username = username
        self.password = password
        self.runner = CommandRunner()

    def get_depots(self, app_id: int, on_output: Optional[Callable[[str], None]] = None) -> DepotManifestsOutput:
        """
        Fetches depot manifests for a given application ID.
        """
        logger.info(f"Fetching depots for app_id: {app_id}")
        app_data_path = self.manifests_data_path

        command = [str(self.binary_path)]

        if self.username:
            command.extend(["-username", self.username])

        if self.password:
            command.extend(["-password", self.password, "-remember-password"])

        command.extend([
            "-app", str(app_id),
            "-manifest-only",
            "-dir", str(app_data_path),
            "-all-platforms",
            "-all-archs",
            "-all-languages",
        ])

        sensitive_values = []
        if self.password:
            sensitive_values.append(self.password)

        output = self.runner.run(
            command,
            sensitive_values=sensitive_values,
            on_output=on_output
        )

        if not output.success:
            logger.error(f"Command failed with code {output.exit_code}")
            raise SubprocessError(f"Command failed with code {output.exit_code}\nSTDOUT: {output.stdout}")

        logger.info(f"Command completed successfully")
        return DepotManifestsOutput.from_output(output, manifest_path=app_data_path)


if __name__ == '__main__':
    login = os.environ.get("LOGIN", "")
    password = os.environ.get("PASSWORD", "")

    downloader = DepotDownloader(debug=False, username=login, password=password)
    try:
        # Use a lambda to print each char in real-time
        output = downloader.get_depots(214950, on_output=lambda char: print(char, end="", flush=True))
        print(f"\nFinal Exit Code: {output.exit_code}")
        print(f"Masked Command: {output.command_str}")
        print(f"Manifests saved to: {output.manifest_path}")
    except SubprocessError:
        sys.exit(1)
