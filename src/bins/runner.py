import subprocess
import sys
from typing import List, Optional, Callable
from dataclasses import dataclass
from src.logger import logger
from src.errors.errors import SubprocessError

@dataclass
class BinOutput:
    """
    Encapsulates the output of a binary command execution.
    """
    command: List[str]
    stdout: str
    stderr: str
    exit_code: int

    @property
    def success(self) -> bool:
        """Returns True if the command exited successfully (code 0)."""
        return self.exit_code == 0

    @property
    def command_str(self) -> str:
        """Returns the masked command as a single string."""
        return " ".join(self.command)

    @classmethod
    def from_output(cls, output: 'BinOutput', **kwargs):
        """
        Creates an instance of the class (or subclass) from an existing BinOutput.
        """
        return cls(
            command=output.command,
            stdout=output.stdout,
            stderr=output.stderr,
            exit_code=output.exit_code,
            **kwargs
        )


class CommandRunner:
    """
    A generic runner for executing external binaries with real-time output streaming.
    """

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._stopped = False

    def stop(self):
        """Signals the runner to stop the current process."""
        self._stopped = True
        if self._proc:
            logger.info("Killing process...")
            try:
                self._proc.kill()
            except Exception as e:
                logger.warning(f"Failed to kill process: {e}")

    def run(
        self,
        command: List[str],
        sensitive_values: Optional[List[str]] = None,
        on_output: Optional[Callable[[str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> BinOutput:
        """
        Executes a command and captures its output.

        Args:
            command: The command and its arguments as a list of strings.
            sensitive_values: A list of values that should be masked with '***' in logs and BinOutput.
            on_output: An optional callback that receives each character of the output in real-time.
            is_cancelled: An optional callback that returns True if the command should be cancelled.

        Returns:
            A BinOutput object containing the execution results.

        Raises:
            SubprocessError: If the command fails to start.
        """
        self._stopped = False
        self._proc = None

        # Create a safe command for logging and BinOutput
        safe_command = command.copy()
        if sensitive_values:
            # Filter out empty strings to avoid accidental over-masking
            real_sensitive = [str(v) for v in sensitive_values if v]
            for i, arg in enumerate(safe_command):
                if any(s == arg for s in real_sensitive):
                    safe_command[i] = "***"

        logger.info(f"Executing command: {' '.join(safe_command)}")

        full_output = []
        try:
            # Using Popen for streaming output and interleaving stdout/stderr
            with subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=sys.stdin, # Allow interactive input if needed
                text=True,
                bufsize=0, # Unbuffered
                universal_newlines=True
            ) as proc:
                self._proc = proc
                if proc.stdout:
                    while True:
                        if self._stopped or (is_cancelled and is_cancelled()):
                            logger.info("Runner stopped or cancellation requested, killing process.")
                            self._stopped = True # Ensure it's marked as stopped if it came from callback
                            proc.kill()
                            break

                        char = proc.stdout.read(1)
                        if not char:
                            break
                        
                        full_output.append(char)
                        if on_output:
                            on_output(char)
                
                proc.wait()
                exit_code = proc.returncode
                stdout = "".join(full_output)

                if self._stopped:
                    logger.info("Command was cancelled by user.")
                else:
                    logger.info(f"Command completed with exit code {exit_code}")
                
                return BinOutput(
                    command=safe_command,
                    stdout=stdout,
                    stderr="", # Combined into stdout via stderr=subprocess.STDOUT
                    exit_code=exit_code
                )
        except Exception as e:
            if self._stopped:
                logger.info("Process termination during stop.")
                return BinOutput(
                    command=safe_command,
                    stdout="".join(full_output),
                    stderr=str(e),
                    exit_code=-1
                )
            logger.error(f"Failed to execute command: {e}")
            raise SubprocessError(f"Failed to execute command: {e}") from e
        finally:
            self._proc = None
