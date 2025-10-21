"""Update Plugin for WordOps - Refactored Version

This module handles WordOps self-update functionality with improved
error handling, security, and reliability.
"""

import os
import subprocess
import time
from typing import Optional, Tuple

from cement.core.controller import CementBaseController, expose
from wo.core.download import WODownload
from wo.core.fileutils import WOFileUtils
from wo.core.logging import Log
from wo.core.variables import WOVar


def wo_update_hook(app) -> None:
    """Hook function for update operations."""
    pass


class UpdateManager:
    """Manages WordOps update operations with proper error handling."""

    # Repository configuration
    REPO_OWNER = "pyrognomic"
    REPO_NAME = "WordOps"
    REPO_FULL = f"{REPO_OWNER}/{REPO_NAME}"
    REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
    RAW_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"

    # Paths
    TMP_DIR = "/var/lib/wo/tmp"

    def __init__(self, controller: 'WOUpdateController'):
        """Initialize UpdateManager.

        Args:
            controller: The WOUpdateController instance
        """
        self.controller = controller
        self.pargs = controller.app.pargs

    def get_current_version(self) -> str:
        """Get the currently installed WordOps version.

        Returns:
            Current version string with 'v' prefix (e.g., 'v3.22.0')
        """
        return f"v{WOVar.wo_version}"

    def get_latest_version(self) -> Optional[str]:
        """Get the latest WordOps release version from GitHub.

        Returns:
            Latest version string or None if query fails
        """
        try:
            return WODownload.latest_release(self.controller, self.REPO_FULL)
        except Exception as e:
            Log.debug(self.controller, f"Failed to get latest version: {e}")
            return None

    def is_update_needed(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Check if an update is needed.

        Returns:
            Tuple of (update_needed: bool, current_version: str, latest_version: str)
        """
        current = self.get_current_version()
        latest = self.get_latest_version()

        if latest is None:
            Log.warning(self.controller, "Unable to check for updates")
            return (False, current, None)

        return (current != latest, current, latest)

    def build_install_args(self) -> Tuple[str, str]:
        """Build arguments for the install script based on user options.

        Returns:
            Tuple of (install_args: str, branch: str)
        """
        install_args = ""
        wo_branch = "master"

        if self.pargs.mainline or self.pargs.beta:
            wo_branch = "mainline"
            install_args += "--mainline "
        elif self.pargs.branch:
            wo_branch = self.pargs.branch
            install_args += f"-b {wo_branch} "

        if self.pargs.force:
            install_args += "--force "

        if self.pargs.travis:
            install_args += "--travis "
            # Note: This seems like a development leftover
            wo_branch = "updating-configuration"

        return install_args.strip(), wo_branch

    def confirm_update(self, latest_version: Optional[str]) -> bool:
        """Prompt user to confirm update.

        Args:
            latest_version: The version to update to

        Returns:
            True if user confirms, False otherwise
        """
        if self.pargs.force:
            return True

        if latest_version:
            changelog_url = f"{self.REPO_URL}/releases/tag/{latest_version}"
            Log.info(self.controller, f"WordOps changelog available on {changelog_url}")

        try:
            response = input("Do you want to continue:[y/N] ")
            return response.lower() in ('y', 'yes')
        except (EOFError, KeyboardInterrupt):
            Log.info(self.controller, "\nUpdate cancelled by user")
            return False

    def ensure_tmp_directory(self) -> None:
        """Ensure the temporary directory exists.

        Raises:
            OSError: If directory cannot be created
        """
        try:
            if not os.path.isdir(self.TMP_DIR):
                os.makedirs(self.TMP_DIR, mode=0o755)
                Log.debug(self.controller, f"Created temporary directory: {self.TMP_DIR}")
        except OSError as e:
            Log.error(
                self.controller,
                f"Failed to create temporary directory {self.TMP_DIR}: {e}"
            )
            raise

    def download_install_script(self, branch: str, filename: str) -> str:
        """Download the install/update script from GitHub.

        Args:
            branch: Git branch to download from
            filename: Local filename to save as

        Returns:
            Path to downloaded script

        Raises:
            Exception: If download fails
        """
        script_url = f"{self.RAW_URL}/{branch}/install"
        script_path = f"{self.TMP_DIR}/{filename}"

        Log.debug(self.controller, f"Downloading update script from {script_url}")

        try:
            WODownload.download(
                self.controller,
                [[script_url, script_path, "update script"]]
            )
        except Exception as e:
            Log.error(
                self.controller,
                f"Failed to download update script: {e}"
            )
            raise

        if not os.path.isfile(script_path):
            raise FileNotFoundError(f"Downloaded script not found at {script_path}")

        return script_path

    def execute_update_script(self, script_path: str, install_args: str) -> bool:
        """Execute the update script.

        Args:
            script_path: Path to the update script
            install_args: Arguments to pass to the script

        Returns:
            True if update succeeded, False otherwise
        """
        Log.info(self.controller, "Updating WordOps, please wait...")

        try:
            # Build command
            cmd = ["/bin/bash", script_path]
            if install_args:
                cmd.extend(install_args.split())

            Log.debug(self.controller, f"Executing: {' '.join(cmd)}")

            # Execute update script
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600  # 10 minute timeout
            )

            # Log output
            if result.stdout:
                Log.debug(self.controller, f"Update stdout:\n{result.stdout}")
            if result.stderr:
                Log.debug(self.controller, f"Update stderr:\n{result.stderr}")

            if result.returncode != 0:
                Log.error(
                    self.controller,
                    f"Update script failed with exit code {result.returncode}"
                )
                return False

            Log.info(self.controller, "WordOps updated successfully")
            return True

        except subprocess.TimeoutExpired:
            Log.error(self.controller, "Update script timed out after 10 minutes")
            return False
        except FileNotFoundError:
            Log.error(self.controller, "Bash interpreter not found")
            return False
        except Exception as e:
            Log.error(self.controller, f"Failed to execute update script: {e}")
            Log.debug(self.controller, f"Exception details: {str(e)}")
            return False

    def execute_local_install(self) -> bool:
        """Execute local install script (for development).

        Returns:
            True if install succeeded, False otherwise
        """
        Log.info(self.controller, "Updating WordOps from local install\n")
        Log.info(self.controller, "Updating WordOps, please wait...")

        try:
            result = subprocess.run(
                ["/bin/bash", "install", "--travis"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600
            )

            if result.returncode != 0:
                Log.error(
                    self.controller,
                    f"Local install failed with exit code {result.returncode}"
                )
                return False

            return True

        except Exception as e:
            Log.error(self.controller, f"Local install failed: {e}")
            return False

    def cleanup_temp_file(self, filepath: str) -> None:
        """Clean up temporary file.

        Args:
            filepath: Path to file to remove
        """
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
                Log.debug(self.controller, f"Cleaned up temporary file: {filepath}")
        except OSError as e:
            Log.warning(
                self.controller,
                f"Failed to clean up temporary file {filepath}: {e}"
            )

    def perform_update(self) -> None:
        """Perform the complete update process.

        This is the main update workflow that coordinates all steps.
        """
        install_args, wo_branch = self.build_install_args()

        # Check if update is needed (unless forced)
        if not any([self.pargs.force, self.pargs.travis,
                   self.pargs.mainline, self.pargs.beta, self.pargs.branch]):
            update_needed, current, latest = self.is_update_needed()

            if latest is None:
                Log.error(
                    self.controller,
                    "Unable to check for updates. Use --force to update anyway."
                )
                self.controller.app.close(1)

            if not update_needed:
                Log.info(
                    self.controller,
                    f"WordOps {latest} is already installed"
                )
                self.controller.app.close(0)

            Log.info(
                self.controller,
                f"Update available: {current} → {latest}"
            )

            # Get user confirmation
            if not self.confirm_update(latest):
                Log.error(self.controller, "Not starting WordOps update")
                self.controller.app.close(0)
        else:
            # For forced/branch updates, still try to get latest version for display
            _, current, latest = self.is_update_needed()
            if not self.confirm_update(latest):
                Log.error(self.controller, "Not starting WordOps update")
                self.controller.app.close(0)

        # Check for local install script (development mode)
        if os.path.isfile('install'):
            success = self.execute_local_install()
            self.controller.app.close(0 if success else 1)

        # Normal update process
        filename = "woupdate" + time.strftime("%Y%m%d-%H%M%S")
        script_path = f"{self.TMP_DIR}/{filename}"

        try:
            # Ensure temp directory exists
            self.ensure_tmp_directory()

            # Download update script
            script_path = self.download_install_script(wo_branch, filename)

            # Execute update
            success = self.execute_update_script(script_path, install_args)

            # Exit with appropriate code
            self.controller.app.close(0 if success else 1)

        except KeyboardInterrupt:
            Log.info(self.controller, "\nUpdate cancelled by user")
            self.controller.app.close(130)  # Standard exit code for SIGINT

        except Exception as e:
            Log.error(self.controller, f"WordOps update failed: {e}")
            self.controller.app.close(1)

        finally:
            # Always clean up temporary file
            self.cleanup_temp_file(script_path)


class WOUpdateController(CementBaseController):
    """Controller for WordOps self-update functionality."""

    class Meta:
        label = 'wo_update'
        stacked_on = 'base'
        aliases = ['update']
        aliases_only = True
        stacked_type = 'nested'
        description = 'Update WordOps to latest version'
        arguments = [
            (['--force'],
             dict(help='Force WordOps update without confirmation',
                  action='store_true')),
            (['--beta'],
             dict(help='Update WordOps to latest mainline release '
                  '(same as --mainline)',
                  action='store_true')),
            (['--mainline'],
             dict(help='Update WordOps to latest mainline release',
                  action='store_true')),
            (['--branch'],
                dict(help='Update WordOps from a specific repository branch',
                     action='store',
                     nargs='?',
                     const='develop',
                     metavar='BRANCH')),
            (['--travis'],
             dict(help='Argument used only for WordOps development',
                  action='store_true')),
        ]
        usage = "wo update [options]"

    @expose(hide=True)
    def default(self) -> None:
        """Execute the update process.

        This is the main entry point for the update command.
        """
        manager = UpdateManager(self)
        manager.perform_update()


def load(app) -> None:
    """Load the update plugin.

    Args:
        app: The Cement application instance
    """
    # Register the plugin class
    app.handler.register(WOUpdateController)
    # Register a hook to run after arguments are parsed
    app.hook.register('post_argument_parsing', wo_update_hook)
