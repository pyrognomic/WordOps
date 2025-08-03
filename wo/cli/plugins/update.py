import os
import time
import subprocess
import sys

from cement.core.controller import CementBaseController, expose
from wo.core.download import WODownload
from wo.core.logging import Log
from wo.core.variables import WOVar


def wo_update_hook(app):
    pass


class WOUpdateController(CementBaseController):
    class Meta:
        label = 'wo_update'
        stacked_on = 'base'
        aliases = ['update']
        aliases_only = True
        stacked_type = 'nested'
        description = ('update WordOps to latest version')
        arguments = [
            (['--force'],
             dict(help='Force WordOps update', action='store_true')),
            (['--dev'],
             dict(help='Update from the latest commit on your fork', action='store_true')),
            (['--beta'],
             dict(help='Update WordOps to latest mainline release (same than --mainline)', action='store_true')),
            (['--mainline'],
             dict(help='Update WordOps to latest mainline release', action='store_true')),
            (['--branch'],
             dict(help="Update WordOps from a specific repository branch", action='store', const='develop', nargs='?')),
            (['--travis'],
             dict(help='Argument used only for WordOps development', action='store_true')),
        ]
        usage = "wo update [options]"

    @expose(hide=True)
    def default(self):
        pargs = self.app.pargs

        # Determine repo owner for fork or upstream releases
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        git_url = subprocess.run(
            ['git', 'config', '--get', 'remote.origin.url'],
            cwd=repo_root,
            capture_output=True,
            text=True
        ).stdout.strip()
        if git_url.startswith('git@'):
            owner = git_url.split(':', 1)[1].split('/', 1)[0]
        else:
            owner = git_url.rstrip('.git').split('/')[-2]

        # Dev mode: pull latest commits from fork and exit
        if pargs.dev:
            Log.wait(self, "Pulling latest commits from fork")
            try:
                subprocess.run(
                    ['git', 'pull'],
                    cwd=repo_root,
                    check=True,
                    capture_output=True,
                    text=True
                )
                Log.valide(self, "Pulling latest commits from fork")
                self.app.close(0)
            except subprocess.CalledProcessError as e:
                Log.failed(self, "Pulling latest commits")
                Log.error(self, e.stderr.strip())
                sys.exit(1)

        filename = "woupdate" + time.strftime("%Y%m%d-%H%M%S")
        install_args = ""

        wo_branch = "master"
        if pargs.mainline or pargs.beta:
            wo_branch = "mainline"
            install_args += "--mainline "
        elif pargs.branch:
            wo_branch = pargs.branch
            install_args += f"-b {wo_branch} "
        if pargs.force:
            install_args += "--force "
        if pargs.travis:
            install_args += "--travis "
            wo_branch = "updating-configuration"

        # check if WordOps already up-to-date
        if ((not pargs.force) and (not pargs.travis) and
            (not pargs.mainline) and (not pargs.beta) and
            (not pargs.branch)):
            wo_current = f"v{WOVar.wo_version}"
            wo_latest = WODownload.latest_release(self, f"{owner}/WordOps")
            if wo_current == wo_latest:
                Log.info(self, f"WordOps {wo_latest} is already installed")
                self.app.close(0)

        # prompt user before starting upgrade
        if not pargs.force:
            Log.info(
                self,
                f"WordOps changelog available on https://github.com/{owner}/WordOps/releases/tag/{wo_latest}"
            )
            start_upgrade = input("Do you want to continue:[y/N] ")
            if start_upgrade not in ("Y", "y"):
                Log.error(self, "Not starting WordOps update")
                sys.exit(0)

        # prepare temp directory and download update script
        if not os.path.isdir('/var/lib/wo/tmp'):
            os.makedirs('/var/lib/wo/tmp')
        WODownload.download(self, [[
            f"https://raw.githubusercontent.com/{owner}/WordOps/{wo_branch}/install",
            f"/var/lib/wo/tmp/{filename}",
            "update script"
        ]])

        # launch install script
        if os.path.isfile('install'):
            Log.info(self, "updating WordOps from local install\n")
            try:
                Log.info(self, "updating WordOps, please wait...")
                os.system("/bin/bash install --travis")
            except OSError as e:
                Log.debug(self, str(e))
                Log.error(self, "WordOps update failed !")
        else:
            try:
                Log.info(self, "updating WordOps, please wait...")
                os.system(f"/bin/bash /var/lib/wo/tmp/{filename} {install_args}")
            except OSError as e:
                Log.debug(self, str(e))
                Log.error(self, "WordOps update failed !")

        os.remove(f"/var/lib/wo/tmp/{filename}")


def load(app):
    # register the plugin class.. this only happens if the plugin is enabled
    app.handler.register(WOUpdateController)
    # register a hook (function) to run after arguments are parsed.
    app.hook.register('post_argument_parsing', wo_update_hook)
