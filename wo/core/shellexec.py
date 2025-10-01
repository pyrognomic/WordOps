"""WordOps Shell Functions"""
import subprocess, re
from typing import Union, Sequence, Optional, Mapping

from wo.core.logging import Log


class CommandExecutionError(Exception):
    """custom Exception for command execution"""
    pass


class WOShellExec:
    """Method to run shell commands"""
    def __init__(self):
        pass

    _SECRET_PATTERNS = [
        r'(--dbpass=)(\S+)', r'(--password=)(\S+)', r'(--pass=)(\S+)',
        r'(--token=)(\S+)', r'(--apikey=)(\S+)', r'(--api-key=)(\S+)', r'(--secret=)(\S+)',
        r'(-p\s+)(\S+)', r'(--password\s+)(\S+)',  # space-separated variants
    ]

    @staticmethod
    def _redact(s: str) -> str:
        import re
        for pat in WOShellExec._SECRET_PATTERNS:
            s = re.sub(pat, r'\1***', s, flags=re.IGNORECASE)
        return s

    @staticmethod
    def cmd_exec(
        controller,
        command: Union[str, Sequence[str]],
        errormsg: str = '',
        log: bool = True,
        input_data: Optional[str] = None,
        timeout: Optional[float] = None,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        shell_executable: Optional[str] = None,
    ) -> bool:
        """Run a shell command. Strings run via shell; sequences run without shell."""
        try:
            use_shell = isinstance(command, str)
            if log:
                shown = command if use_shell else " ".join(map(str, command))
                Log.debug(controller, f"Running command: {WOShellExec._redact(shown)}")

            proc = subprocess.run(
                command,
                input=input_data,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                shell=use_shell,
                executable=(shell_executable if use_shell and shell_executable else None),
                cwd=cwd,
                env=env,
                timeout=timeout,
            )

            if proc.stderr.strip():
                Log.debug(controller, f"Command Output: {proc.stdout}, \nCommand Error: {proc.stderr}")
            else:
                Log.debug(controller, f"Command Output: {proc.stdout}")

            if proc.returncode != 0 and errormsg:
                Log.error(controller, errormsg)

            return proc.returncode == 0

        except subprocess.TimeoutExpired as e:
            Log.debug(controller, f"Timeout: {e}")
            if errormsg:
                Log.error(controller, errormsg)
            return False
        except OSError as e:
            Log.debug(controller, str(e))
            raise CommandExecutionError
        except Exception as e:
            Log.debug(controller, str(e))
            raise CommandExecutionError

    @staticmethod
    def invoke_editor(self, filepath, errormsg=''):
        """
            Open files using sensible editor
        """
        try:
            subprocess.call(['sensible-editor', filepath])
        except OSError as e:
            Log.debug(self, "{0}{1}".format(e.errno, e.strerror))
            raise CommandExecutionError

    @staticmethod
    def cmd_exec_stdout(controller, command, errormsg: str = '', log: bool = True) -> str:
        """Run shell command and return stdout as text (legacy helper)."""
        try:
            if log:
                Log.debug(controller, f"Running command: {WOShellExec._redact(str(command))}")

            # Use string when shell=True, or pass a sequence and set shell=False (recommended).
            use_shell = isinstance(command, str)
            if use_shell:
                proc = subprocess.run(command, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
            else:
                proc = subprocess.run(command, shell=False, capture_output=True, text=True, encoding="utf-8", errors="replace")

            if proc.stderr.strip():
                Log.debug(controller, f"Command Output: {proc.stdout}, \nCommand Error: {proc.stderr}")
            else:
                Log.debug(controller, f"Command Output: {proc.stdout}")

            # Return stdout regardless of rc, to match prior behavior
            if proc.returncode != 0 and errormsg:
                Log.error(controller, errormsg)
            return proc.stdout

        except OSError as e:
            Log.debug(controller, str(e))
            raise CommandExecutionError
        except Exception as e:
            Log.debug(controller, str(e))
            raise CommandExecutionError
