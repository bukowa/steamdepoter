import os
import sys
from src.errors.errors import SubprocessError

class DepotDownloader:

    def __init__(self, binary_path=None, data_path=None, debug=False, username="anonymous", password=""):
        if not binary_path:
            binary_path = os.path.join(os.getcwd(), ".bin", "DepotDownloader")
            if sys.platform == "win32":
                binary_path += ".exe"
        self.binary_path = os.path.abspath(binary_path)

        if not data_path:
            data_path = os.path.join("data", "depots")
        self.data_path = os.path.abspath(data_path)
        self.debug = debug
        self.username = username
        self.password = password

    def _run_command(self, *args, debug=False):
        args = list(args)
        if debug:
            args.append('-debug')

        command = [self.binary_path]
        if self.username:
            command.extend(['-username', self.username])
        if self.password:
            command.extend(['-password', self.password, '-remember-password'])
        command.extend(args)

        import subprocess
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise SubprocessError(f"Command failed with code {result.returncode}: {result.stderr} {result.stdout}")
        return result.stdout

    def get_depots(self, app_id):
        stdout = self._run_command(*[
            '-app', str(app_id),
            '-manifest-only',
            '-dir', os.path.join(self.data_path, str(app_id)),
            '-all-platforms',
            '-all-archs',
            '-all-languages'
        ])
        return stdout




if __name__ == '__main__':
    login = os.environ.get("LOGIN", "anonymous")
    password = os.environ.get("PASSWORD", "")

    downloader = DepotDownloader(debug=True, username=login, password=password)
    depots = downloader.get_depots(325624)
    print(depots)
