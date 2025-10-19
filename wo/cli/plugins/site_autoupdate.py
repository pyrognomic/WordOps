import json
import os
import shutil
import subprocess
import time
import errno
from datetime import datetime

try:
    import pwd  # POSIX-only
except ImportError:  # pragma: no cover - non-POSIX platforms
    pwd = None

from cement.core.controller import CementBaseController, expose

from wo.cli.plugins.sitedb import getAllsites, getSiteInfo
from wo.cli.plugins.site_functions import SiteError
from wo.core.backup import WOBackup
from wo.core.fileutils import WOFileUtils
from wo.core.logging import Log
from wo.core.shellexec import WOShellExec
from wo.core.template import WOTemplate


def _now_ts():
    return datetime.utcnow().strftime('%Y-%m-%d_%H-%M-%S')


class WOSiteAutoUpdateController(CementBaseController):
    class Meta:
        label = 'autoupdate'
        stacked_on = 'site'
        stacked_type = 'nested'
        description = 'Check and apply WordPress updates with automated backup and rollback'
        arguments = [
            (['site_name'], dict(help='domain to process', nargs='?')),
            (['--all'], dict(help='process all WordPress sites', action='store_true')),
            (['--dry-run'], dict(help='only check; do not change anything', action='store_true')),
            (['--no-visual'], dict(help='skip visual regression step', action='store_true')),
            (['--backup-dir'], dict(help='override backup root directory')),
            # BackstopJS setup options
            (['--urls'], dict(help='comma-separated URL paths for scenarios (e.g. /,/about,/contact)')),
            (['--urls-file'], dict(help='file with one URL path per line')),
            (['--reference'], dict(help='generate BackstopJS baseline immediately', action='store_true')),
            (['--approve'], dict(help='promote last BackstopJS test to baseline (when used with backstop command)', action='store_true')),
        ]

    # ----- Public commands -----
    @expose(help='Run autoupdate for the given site or for all WP sites')
    def run(self):
        pargs = self.app.pargs
        # Acquire global run lock to prevent overlapping batches
        global_lock = '/run/wo-autoupdate.lock'
        if not self._acquire_lock(global_lock):
            Log.warn(self, 'Another autoupdate run is in progress; skipping')
            return
        try:
            targets = self._discover_targets(pargs)
            if not targets:
                Log.info(self, 'No sites to process')
                return

            summary = { 'started_at': _now_ts(), 'sites': [] }
            ok_all = True

            for sitename in targets:
                # Per-site lock to avoid concurrent operations on the same site
                site_lock = None
                try:
                    siteinfo = getSiteInfo(self, sitename)
                    if not siteinfo:
                        summary['sites'].append({'site': sitename, 'status': 'error', 'error': 'site not found'})
                        ok_all = False
                        continue

                    slug = siteinfo.sitename.replace('.', '-').lower()
                    site_lock = f'/run/wo-autoupdate-{slug}.lock'
                    if not self._acquire_lock(site_lock):
                        Log.warn(self, f'Skipping {sitename}: another update in progress for this site')
                        summary['sites'].append({'site': sitename, 'status': 'skip', 'reason': 'locked'})
                        continue

                    res = self._process_site(
                        siteinfo,
                        dry_run=pargs.dry_run,
                        skip_visual=pargs.no_visual,
                        backup_root=pargs.backup_dir,
                    )
                    summary['sites'].append(res)
                    if res.get('status') == 'error':
                        ok_all = False
                except Exception as e:
                    Log.debug(self, f'Autoupdate error for {sitename}: {str(e)}')
                    summary['sites'].append({'site': sitename, 'status': 'error', 'error': str(e)})
                    ok_all = False
                finally:
                    if site_lock:
                        self._release_lock(site_lock)

            summary['finished_at'] = _now_ts()
            self._write_summary(summary)
            if not ok_all:
                Log.warn(self, 'One or more sites failed during autoupdate')
        finally:
            self._release_lock(global_lock)

    @expose(help='Install or remove hourly systemd autoupdate timer')
    def schedule(self):
        pargs = self.app.pargs
        # Simple arg parsing: wo site autoupdate schedule [--enable|--disable] [--interval hourly|daily]
        enable = '--enable' in self.app.argv
        disable = '--disable' in self.app.argv
        interval = 'hourly'
        for flag in ('hourly', 'daily'):
            if f'--interval={flag}' in self.app.argv:
                interval = flag
                break

        if enable and disable:
            Log.error(self, 'Cannot use --enable and --disable together')

        service_path = '/etc/systemd/system/wo-autoupdate.service'
        timer_path = '/etc/systemd/system/wo-autoupdate.timer'

        if enable:
            data = {
                'exec': '/usr/local/bin/wo site autoupdate run --all --no-visual',
                'interval': 'OnCalendar=hourly' if interval == 'hourly' else 'OnCalendar=daily',
            }
            WOTemplate.deploy(self, service_path, 'autoupdate-service.mustache', data, overwrite=True)
            WOTemplate.deploy(self, timer_path, 'autoupdate-timer.mustache', data, overwrite=True)
            # Reload and enable timer
            WOShellExec.cmd_exec(self, ['systemctl', 'daemon-reload'], errormsg='failed to reload systemd')
            WOShellExec.cmd_exec(self, ['systemctl', 'enable', '--now', 'wo-autoupdate.timer'], errormsg='failed to enable timer')
            Log.info(self, f'Installed autoupdate timer ({interval})')
            return

        if disable:
            WOShellExec.cmd_exec(self, ['systemctl', 'disable', '--now', 'wo-autoupdate.timer'], errormsg='failed to disable timer')
            for path in (service_path, timer_path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
            WOShellExec.cmd_exec(self, ['systemctl', 'daemon-reload'])
            Log.info(self, 'Removed autoupdate timer')
            return

        Log.info(self, 'Usage: wo site autoupdate schedule --enable|--disable [--interval=hourly|daily]')

    # ----- Internal helpers -----
    def _discover_targets(self, pargs):
        if pargs.all:
            targets = []
            for s in getAllsites(self) or []:
                # Only WordPress site types
                if s.site_type and 'wp' in s.site_type:
                    targets.append(s.sitename)
            return targets

        if pargs.site_name:
            return [pargs.site_name.strip()]

        return []

    def _ensure_dirs(self, siteinfo):
        slug = siteinfo.sitename.replace('.', '-').lower()
        base = os.path.join('/var/log/wo/autoupdate', slug)
        WOFileUtils.mkdir(self, base)
        return base

    def _backup_site(self, siteinfo, backup_root=None, update_info=None, has_updates=False):
        """Create a backup using the centralized backup service.

        Args:
            siteinfo: Site information object
            backup_root: Optional custom backup directory
            update_info: Dict with update details for metadata
            has_updates: Whether WordPress updates are available

        Returns:
            Tuple of (success: bool, archive_path: str or None)
        """
        # Prepare metadata
        metadata_extra = {
            'timestamp': _now_ts()
        }

        # Set backup type and add update information if updates exist
        if has_updates:
            metadata_extra['backup_type'] = 'pre-update'
            if update_info:
                metadata_extra['pending_updates'] = update_info
        else:
            metadata_extra['backup_type'] = 'scheduled'

        backup_service = WOBackup(self, siteinfo)
        success, archive = backup_service.create(
            backup_type=WOBackup.TYPE_FULL,
            backup_root=backup_root,
            metadata_extra=metadata_extra
        )

        # Rename archive to include "preupdate" if updates exist
        if success and archive and has_updates:
            archive = self._rename_backup_with_preupdate(archive)

        if success:
            if has_updates:
                Log.info(self, f"Pre-update backup created: {archive}")
            else:
                Log.info(self, f"Scheduled backup created: {archive}")
        else:
            Log.error(self, f"Backup failed for {siteinfo.sitename}")

        return success, archive

    def _rename_backup_with_preupdate(self, archive_path):
        """Rename backup archive to include 'preupdate' in filename.

        Args:
            archive_path: Original archive path

        Returns:
            New archive path with 'preupdate' in name
        """
        import os
        import shutil

        try:
            # Parse the original path
            # Format: /path/to/site/backup/example.com/2025-01-20_14-25-30.tar.zst
            directory = os.path.dirname(archive_path)
            filename = os.path.basename(archive_path)

            # Extract timestamp and extension
            # Format: 2025-01-20_14-25-30.tar.zst
            if filename.endswith('.tar.zst'):
                timestamp = filename[:-8]  # Remove .tar.zst
                new_filename = f"{timestamp}_preupdate.tar.zst"
            else:
                # Fallback if format is different
                new_filename = filename.replace('.tar.zst', '_preupdate.tar.zst')

            new_path = os.path.join(directory, new_filename)

            # Rename the file
            shutil.move(archive_path, new_path)
            Log.debug(self, f"Renamed backup: {filename} -> {new_filename}")

            return new_path

        except Exception as e:
            Log.debug(self, f"Failed to rename backup: {str(e)}")
            # Return original path if rename fails
            return archive_path

    def _site_slug(self, siteinfo):
        return siteinfo.sitename.replace('.', '-').lower()

    def _site_user(self, siteinfo):
        return f'php-{self._site_slug(siteinfo)}'

    def _wp_cli_run(self, siteinfo, args, **kwargs):
        """Execute a WP-CLI command as the site's PHP-FPM user to keep permissions consistent.

        Raises:
            SiteError: if the platform cannot switch users or the expected site user is missing.
        """
        user = self._site_user(siteinfo)

        # Prepare environment overrides without mutating caller data
        env_override = kwargs.pop('env', None)
        final_env = os.environ.copy()
        if env_override:
            final_env.update(env_override)

        if pwd is None:
            raise SiteError('WP-CLI commands require POSIX user management to switch to the site owner')

        # Ensure we're running as root before attempting privilege drop
        if os.getuid() != 0:
            raise SiteError('WP-CLI user switching requires running as root')

        try:
            pw_entry = pwd.getpwnam(user)
        except KeyError:
            raise SiteError(f'Site PHP-FPM user {user} not found; aborting WP-CLI operation')

        slug = self._site_slug(siteinfo)
        wp_home = os.path.join('/tmp', f'wp-cli-{slug}')
        cache_dir = os.path.join(wp_home, 'cache')
        config_path = os.path.join(wp_home, 'wp-cli.yml')

        for path in (wp_home, cache_dir):
            try:
                os.makedirs(path, exist_ok=True)
                if hasattr(os, 'chown'):
                    os.chown(path, pw_entry.pw_uid, pw_entry.pw_gid)
            except PermissionError:
                Log.debug(self, f'Unable to adjust ownership for {path}; continuing with existing permissions')
            except OSError as e:
                Log.debug(self, f'Failed to prepare WP-CLI path {path}: {str(e)}')

        final_env.setdefault('HOME', wp_home)
        final_env.setdefault('WP_CLI_CACHE_DIR', cache_dir)
        final_env.setdefault('WP_CLI_CONFIG_PATH', config_path)
        kwargs['env'] = final_env

        can_switch = all(hasattr(os, attr) for attr in ('getuid', 'setuid', 'setgid'))
        if not can_switch:
            raise SiteError(f'User switching not supported on this platform; cannot run WP-CLI as {user}')

        def demote():
            if hasattr(os, 'initgroups'):
                try:
                    os.initgroups(user, pw_entry.pw_gid)
                except OSError as e:
                    Log.debug(self, f'initgroups failed for {user}: {str(e)}')
            os.setgid(pw_entry.pw_gid)
            os.setuid(pw_entry.pw_uid)
            os.umask(0o022)  # Ensure files are created with proper permissions

        kwargs['preexec_fn'] = demote
        return subprocess.run(args, **kwargs)

    def _run_wp_json(self, siteinfo, cwd, args):
        try:
            proc = self._wp_cli_run(siteinfo, args, cwd=cwd, text=True, capture_output=True)
            stdout = proc.stdout.strip()
            if proc.returncode != 0:
                Log.debug(self, f'WP-CLI error: {proc.stderr}')
                return proc.returncode, None
            data = json.loads(stdout) if stdout else []
            return 0, data
        except Exception as e:
            Log.debug(self, f'_run_wp_json failed: {str(e)}')
            return 1, None

    def _check_updates(self, siteinfo):
        """Check for available updates using WordPress dashboard methods.

        This uses the same approach as wp-admin/update-core.php:
        - get_core_updates() for WordPress core
        - get_plugin_updates() for plugins
        - get_theme_updates() for themes

        These functions require wp-admin includes and are more reliable than
        parsing WP-CLI output directly.
        """
        htdocs = os.path.join(siteinfo.site_path, 'htdocs')
        wp = '/usr/local/bin/wp'
        need = {'core': False, 'plugins': [], 'themes': []}

        # Use wp eval with the WordPress admin update functions
        # This is the same method used by the WordPress dashboard
        check_script = """
require_once ABSPATH . 'wp-admin/includes/update.php';
require_once ABSPATH . 'wp-admin/includes/plugin.php';
require_once ABSPATH . 'wp-admin/includes/theme.php';

// Force fresh update checks (like dashboard does with ?force-check=1)
wp_update_plugins();
wp_update_themes();
wp_version_check(array(), true);

$result = array(
    'core' => array(),
    'plugins' => array(),
    'themes' => array()
);

// Core updates (same as update-core.php:246)
$core_updates = get_core_updates();
if (!empty($core_updates)) {
    foreach ($core_updates as $update) {
        if (isset($update->response) && $update->response !== 'latest') {
            $result['core'][] = array(
                'version' => $update->version,
                'current' => isset($update->current) ? $update->current : '',
                'response' => $update->response
            );
        }
    }
}

// Plugin updates (same as update-core.php:467)
$plugin_updates = get_plugin_updates();
if (!empty($plugin_updates)) {
    foreach ($plugin_updates as $plugin_file => $plugin_data) {
        $result['plugins'][] = array(
            'name' => $plugin_data->Name,
            'file' => $plugin_file,
            'current' => $plugin_data->Version,
            'new' => $plugin_data->update->new_version
        );
    }
}

// Theme updates (same as update-core.php:640)
$theme_updates = get_theme_updates();
if (!empty($theme_updates)) {
    foreach ($theme_updates as $stylesheet => $theme) {
        $result['themes'][] = array(
            'name' => $theme->get('Name'),
            'stylesheet' => $stylesheet,
            'current' => $theme->get('Version'),
            'new' => isset($theme->update['new_version']) ? $theme->update['new_version'] : ''
        );
    }
}

echo json_encode($result, JSON_PRETTY_PRINT);
"""

        cmd = [wp, 'eval', check_script]
        rc, update_data = self._run_wp_json(siteinfo, htdocs, cmd)

        if rc == 0 and update_data:
            # Core updates
            core_updates = update_data.get('core', [])
            need['core'] = len(core_updates) > 0

            # Plugin updates
            plugin_updates = update_data.get('plugins', [])
            need['plugins'] = [p['name'] for p in plugin_updates]

            # Theme updates
            theme_updates = update_data.get('themes', [])
            need['themes'] = [t['name'] for t in theme_updates]

            # Log detailed update information
            if need['core']:
                for upd in core_updates:
                    Log.debug(self, f"Core update available: {upd.get('current')} -> {upd.get('version')}")
            for p in plugin_updates:
                Log.debug(self, f"Plugin update: {p['name']}: {p['current']} -> {p['new']}")
            for t in theme_updates:
                Log.debug(self, f"Theme update: {t['name']}: {t['current']} -> {t['new']}")
        else:
            Log.warn(self, f"Failed to check updates using WordPress functions (rc={rc})")

        return need

    def _perform_updates(self, siteinfo, logdir):
        htdocs = os.path.join(siteinfo.site_path, 'htdocs')
        wp = '/usr/local/bin/wp'
        results = {'core': None, 'plugins': None, 'themes': None}

        def run_and_log(name, args):
            logfile = os.path.join(logdir, f'{name}.log')
            try:
                with open(logfile, 'w', encoding='utf-8') as fh:
                    proc = self._wp_cli_run(siteinfo, args, cwd=htdocs, text=True, capture_output=True)
                    fh.write(proc.stdout)
                    if proc.stderr:
                        fh.write('\nSTDERR:\n')
                        fh.write(proc.stderr)
                return proc.returncode == 0
            except Exception as e:
                Log.debug(self, f'run_and_log {name} failed: {str(e)}')
                return False

        # core
        results['core'] = run_and_log('core', [wp, 'core', 'update'])
        # plugins
        results['plugins'] = run_and_log('plugins', [wp, 'plugin', 'update', '--all'])
        # themes
        results['themes'] = run_and_log('themes', [wp, 'theme', 'update', '--all'])

        return results

    def _visual_regression(self, siteinfo, logdir):
        cmd_file = os.path.join(siteinfo.site_path, 'conf', 'autoupdate-visual-cmd')
        env = os.environ.copy()
        env['WO_SITE'] = siteinfo.sitename
        env['WO_WEBROOT'] = siteinfo.site_path
        logfile = os.path.join(logdir, 'visual-regression.log')

        # Per-site command hook
        if os.path.isfile(cmd_file):
            with open(cmd_file, 'r', encoding='utf-8') as fh:
                cmd = fh.read().strip()
            try:
                proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, env=env)
                with open(logfile, 'w', encoding='utf-8') as f:
                    f.write(proc.stdout)
                    if proc.stderr:
                        f.write('\nSTDERR:\n')
                        f.write(proc.stderr)
                return proc.returncode == 0
            except Exception as e:
                Log.debug(self, f'visual regression hook failed: {str(e)}')
                return False

        # No configured tool; skip
        Log.debug(self, 'No visual regression command configured; skipping')
        return True

    def _restore_backup(self, archive_path):
        # Delegate to existing restore command
        return WOShellExec.cmd_exec(self, ['wo', 'site', 'restore', archive_path], errormsg='restore failed')

    def _write_summary(self, summary):
        base = '/var/log/wo/autoupdate'
        try:
            WOFileUtils.mkdir(self, base)
            path = os.path.join(base, f'run-{_now_ts()}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2)
        except Exception:
            pass

    def _process_site(self, siteinfo, dry_run=False, skip_visual=False, backup_root=None):
        site = siteinfo.sitename
        slug = site.replace('.', '-').lower()
        logdir = self._ensure_dirs(siteinfo)

        result = {
            'site': site,
            'status': 'ok',
            'checked_at': _now_ts(),
            'updates': {'core': False, 'plugins': 0, 'themes': 0},
            'backup': None,
            'rolled_back': False,
        }

        if not (siteinfo.site_type and 'wp' in siteinfo.site_type):
            result['status'] = 'skip'
            result['reason'] = 'non-wordpress'
            return result

        # Check for updates first
        need = self._check_updates(siteinfo)
        result['updates'] = {
            'core': bool(need.get('core')),
            'plugins': len(need.get('plugins') or []),
            'themes': len(need.get('themes') or []),
        }

        has_updates = bool(need['core'] or need['plugins'] or need['themes'])

        if dry_run:
            result['status'] = 'planned' if has_updates else 'noop'
            return result

        # ALWAYS backup (even if no updates)
        # Metadata and archive name will differ based on whether updates exist
        update_info = {
            'core': need.get('core', False),
            'plugins': need.get('plugins', []),
            'themes': need.get('themes', []),
        }

        backup_ok, archive = self._backup_site(
            siteinfo,
            backup_root=backup_root,
            update_info=update_info,
            has_updates=has_updates  # Pass this to control archive naming
        )
        result['backup'] = archive

        if not backup_ok:
            result['status'] = 'error'
            result['error'] = 'backup failed'
            return result

        # If no updates available, exit after backup
        if not has_updates:
            Log.info(self, f"No updates available for {site}, backup created")
            result['status'] = 'backup-only'
            return result

        # Pre-update: ensure latest BackstopJS reference from current site state (if configured)
        self._generate_backstop_reference(siteinfo)

        # Apply updates (only if available)
        upd = self._perform_updates(siteinfo, logdir)
        if not all(upd.values()):
            Log.warn(self, f'Update step failed for {site}; attempting restore')
            if archive:
                if self._restore_backup(archive):
                    result['rolled_back'] = True
            result['status'] = 'error'
            result['error'] = 'update failed'
            return result

        # Visual regression
        if not skip_visual:
            vr_ok = self._visual_regression(siteinfo, logdir)
            if not vr_ok:
                Log.warn(self, f'Visual regression failed for {site}; attempting restore')
                if archive:
                    if self._restore_backup(archive):
                        result['rolled_back'] = True
                result['status'] = 'error'
                result['error'] = 'visual regression failed'
                return result

        return result

    def _refresh_backstop_reference(self, siteinfo):
        try:
            conf_dir = os.path.join(siteinfo.site_path, 'conf')
            cfg = os.path.join(conf_dir, 'backstop.config.js')
            if os.path.isfile(cfg):
                # Prefer approve to promote last successful test images
                ok = WOShellExec.cmd_exec(self, ['npx', 'backstop', 'approve', f'--config={cfg}'])
                if not ok:
                    # Fallback to regenerating reference
                    WOShellExec.cmd_exec(self, ['npx', 'backstop', 'reference', f'--config={cfg}'])
        except Exception as e:
            Log.debug(self, f'refresh reference failed: {str(e)}')

    def _generate_backstop_reference(self, siteinfo):
        try:
            conf_dir = os.path.join(siteinfo.site_path, 'conf')
            cfg = os.path.join(conf_dir, 'backstop.config.js')
            if os.path.isfile(cfg):
                WOShellExec.cmd_exec(self, ['npx', 'backstop', 'reference', f'--config={cfg}'])
        except Exception as e:
            Log.debug(self, f'pre-update reference failed: {str(e)}')

    # ----- Lock helpers -----
    def _acquire_lock(self, path, max_age_sec=6*60*60):
        """Attempt to create a lock file atomically. Clean up stale locks.

        The lock file contains JSON with pid and timestamp for debugging.
        Returns True on success, False if another holder is active.
        """
        try:
            # Fast path: try atomic create
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                payload = {'pid': os.getpid(), 'ts': time.time(), 'argv': self.app.argv}
                os.write(fd, json.dumps(payload).encode('utf-8'))
            finally:
                os.close(fd)
            return True
        except OSError as e:
            if e.errno != errno.EEXIST:
                Log.debug(self, f'lock open error for {path}: {str(e)}')
                return False

        # Lock exists; check staleness
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            pid = int(data.get('pid', 0))
            ts = float(data.get('ts', 0))
        except Exception:
            pid, ts = 0, 0.0

        stale = False
        # Age check
        if ts and (time.time() - ts > max_age_sec):
            stale = True
        # PID liveness check (POSIX)
        if pid:
            try:
                os.kill(pid, 0)
                # Process exists; not stale on pid
            except OSError:
                stale = True

        if stale:
            try:
                os.remove(path)
            except OSError:
                pass
            # Retry create once
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                try:
                    payload = {'pid': os.getpid(), 'ts': time.time(), 'argv': self.app.argv, 'recovered': True}
                    os.write(fd, json.dumps(payload).encode('utf-8'))
                finally:
                    os.close(fd)
                Log.warn(self, f'Recovered stale lock: {path}')
                return True
            except OSError:
                return False

        return False

    def _release_lock(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def load(app):
    app.handler.register(WOSiteAutoUpdateController)

    # Add subcommand to scaffold BackstopJS config and hook
    @expose(help='Setup BackstopJS for a site (config + autoupdate hook)')
    def backstop(self):
        pargs = self.app.pargs

        targets = self._discover_targets(pargs) if pargs.all else []
        if not targets:
            if not pargs.site_name:
                try:
                    while not pargs.site_name:
                        pargs.site_name = input('Enter site name : ').strip()
                except IOError as e:
                    Log.debug(self, str(e))
                    Log.error(self, 'Unable to input site name, Please try again!')
            targets = [pargs.site_name.strip()]

        created = 0
        for name in targets:
            siteinfo = getSiteInfo(self, name)
            if not siteinfo or not (siteinfo.site_type and 'wp' in siteinfo.site_type):
                Log.warn(self, f'Skipping {name}: not a WordPress site or not found')
                continue

            conf_dir = os.path.join(siteinfo.site_path, 'conf')
            WOFileUtils.mkdir(self, conf_dir)

            base_url = ('https' if siteinfo.is_ssl else 'http') + f'://{siteinfo.sitename}'

            # Resolve scenarios
            paths = []
            if pargs.urls:
                parts = [p.strip() for p in pargs.urls.split(',') if p.strip()]
                paths.extend(parts)
            if pargs.urls_file and os.path.isfile(pargs.urls_file):
                try:
                    with open(pargs.urls_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            s = line.strip()
                            if s:
                                paths.append(s)
                except OSError as e:
                    Log.warn(self, f'Could not read urls file: {str(e)}')
            if not paths:
                paths = ['/']

            scenarios = []
            for i, p in enumerate(paths):
                if not p.startswith('http'):
                    # join base URL and path
                    url = base_url.rstrip('/') + ('/' + p.lstrip('/'))
                else:
                    url = p
                scenarios.append({
                    'label': p if p != '/' else 'home',
                    'url': url,
                    'misMatchThreshold': 0.05,
                    'requireSameDimensions': 'true'  # rendered verbatim
                })

            slug = siteinfo.sitename.replace('.', '-').lower()
            config_path = os.path.join(conf_dir, 'backstop.config.js')
            paths_root = os.path.join(conf_dir, 'backstop_data')
            paths_root_js = paths_root.replace('\\', '/')

            # Prepare data for mustache
            # Cement/mustache will render lists; ensure no trailing commas via a 'last' flag
            ms_scenarios = []
            for idx, sc in enumerate(scenarios):
                ms_scenarios.append({
                    'label': sc['label'],
                    'url': sc['url'],
                    'misMatchThreshold': sc['misMatchThreshold'],
                    'requireSameDimensions': sc['requireSameDimensions'],
                    'last': (idx == len(scenarios) - 1)
                })

            data = {
                'slug': slug,
                'scenarios': ms_scenarios,
                'paths_root': paths_root_js,
            }

            # Write BackstopJS config
            WOTemplate.deploy(self, config_path, 'backstop.config.js.mustache', data, overwrite=True)

            # Create autoupdate hook to run tests
            hook_path = os.path.join(conf_dir, 'autoupdate-visual-cmd')
            hook_data = { 'config_path': config_path }
            WOTemplate.deploy(self, hook_path, 'autoupdate-visual-cmd.mustache', hook_data, overwrite=True)

            Log.info(self, f'BackstopJS configured for {name}: {config_path}')

            # Optionally generate or approve baseline
            if pargs.approve:
                ok = WOShellExec.cmd_exec(self, ['npx', 'backstop', 'approve', f'--config={config_path}'], errormsg='backstop approve failed')
                if not ok:
                    Log.warn(self, 'Failed to approve latest test as baseline')
            elif pargs.reference:
                ok = WOShellExec.cmd_exec(self, ['npx', 'backstop', 'reference', f'--config={config_path}'], errormsg='backstop reference failed')
                if not ok:
                    Log.warn(self, 'Failed to generate baseline (backstop reference)')
            created += 1

        Log.info(self, f'BackstopJS setup completed for {created} site(s)')

    # Bind method onto controller class so Cement can find it
    setattr(WOSiteAutoUpdateController, 'backstop', backstop)
