import getpass
import os
import pwd
import socket
import sys

from cement.core.controller import CementBaseController, expose

from wo.core.git import WOGit
from wo.core.logging import Log
from wo.core.services import WOService
from wo.core.shellexec import WOShellExec
from wo.core.template import WOTemplate

SSH_CONFIG_PATHS = ['/etc/ssh/sshd_config', '/etc/ssh/ssh_config']
SSH_DROPIN_DIR = '/etc/ssh/sshd_config.d'
SSH_DROPIN_PATH = os.path.join(SSH_DROPIN_DIR, '00-hardening.conf')
HOSTS_PATH = '/etc/hosts'


class WOSecureController(CementBaseController):
    class Meta:
        label = 'secure'
        stacked_on = 'base'
        stacked_type = 'nested'
        description = 'Security related operations.'
        arguments = [
            (['--hostname'], dict(help='Hostname to configure', action='store')),
            (['--user'], dict(help='SSH user to create', action='store')),
            (['--port'], dict(help='SSH port to enforce', action='store')),
            (['--allow-password'], dict(help='Allow SSH password authentication', action='store_true')),
            (['--force'], dict(help='Run without confirmation prompt', action='store_true')),
        ]

    @expose(hide=True)
    def default(self):
        self.app.args.print_help()

    @expose(help='Harden SSH access, set the hostname and provision an admin user.')
    def ssh(self):
        pargs = self.app.pargs

        hostname = (pargs.hostname or input(
            f"System hostname [{socket.gethostname()}]: ").strip() or socket.gethostname())
        if not hostname:
            Log.error(self, 'Hostname is required to harden SSH.')

        username = (pargs.user or input('Administrative SSH username [admin]: ').strip() or 'admin')
        if not username:
            Log.error(self, 'A non-empty SSH username is required.')

        port = pargs.port or input('SSH port [22]: ').strip() or '22'
        port = self._validate_port(port)

        allow_password = bool(pargs.allow_password)

        if not pargs.force:
            Log.info(self, f'Hostname will be set to {hostname}')
            Log.info(self, f'SSH user to provision: {username}')
            Log.info(self, f'SSH port to enforce: {port}')
            Log.info(self, f'Allow password authentication: {"yes" if allow_password else "no"}')
            proceed = input('Apply SSH hardening with these settings? [y/N]: ').strip()
            if proceed.lower() != 'y':
                Log.info(self, 'Aborted SSH hardening at user request.')
                return

        password = self._prompt_password(username)

        self._set_hostname(hostname)
        self._ensure_hosts_entry(hostname)
        self._provision_user(username, password)
        self._render_sshd_config(username, port, allow_password)

        Log.info(self, 'Successfully applied SSH hardening and system adjustments.')

    def _validate_port(self, port: str) -> str:
        if not port.isdigit():
            Log.error(self, f'Invalid SSH port: {port}')
        value = int(port)
        if value < 1 or value > 65535:
            Log.error(self, f'SSH port must be between 1 and 65535, got {value}')
        return str(value)

    def _prompt_password(self, username: str) -> str:
        while True:
            password = getpass.getpass(f'Password for {username}: ')
            if not password:
                Log.warn(self, 'Password cannot be empty.')
                continue
            confirm = getpass.getpass('Confirm password: ')
            if password != confirm:
                Log.warn(self, 'Passwords do not match, please try again.')
                continue
            return password

    def _set_hostname(self, hostname: str) -> None:
        if not WOShellExec.cmd_exec(self, ['hostnamectl', 'set-hostname', hostname]):
            Log.error(self, f'Failed to set hostname to {hostname}')

    def _ensure_hosts_entry(self, hostname: str) -> None:
        entry = f'127.0.1.1 {hostname}\n'
        try:
            existing = ''
            if os.path.isfile(HOSTS_PATH):
                with open(HOSTS_PATH, encoding='utf-8') as handle:
                    existing = handle.read()
            if hostname not in existing:
                with open(HOSTS_PATH, 'a', encoding='utf-8') as handle:
                    handle.write(entry)
        except OSError as error:
            Log.error(self, f'Failed to update {HOSTS_PATH}: {error}')

    def _ensure_sshd_include(self) -> None:
        include_line = f'Include {SSH_DROPIN_DIR}/*.conf'
        stripped_include = include_line.strip()

        for config_path in SSH_CONFIG_PATHS:
            if not os.path.isfile(config_path):
                Log.debug(self, f'SSH config file not found at {config_path}, skipping.')
                continue

            try:
                with open(config_path, encoding='utf-8') as handle:
                    lines = handle.readlines()
            except OSError as error:
                Log.warn(self, f'Failed to read {config_path}: {error}')
                continue

            # Check if Include directive already exists at the end
            last_nonempty = ''
            for line in reversed(lines):
                if line.strip():
                    last_nonempty = line.strip()
                    break

            if last_nonempty == stripped_include:
                Log.debug(self, f'Include directive already at end of {config_path}')
                continue

            # Remove existing Include directive if present elsewhere
            filtered_lines = [line for line in lines if line.strip() != stripped_include]

            # Remove trailing empty lines
            while filtered_lines and not filtered_lines[-1].strip():
                filtered_lines.pop()

            # Ensure last line has newline
            if filtered_lines and not filtered_lines[-1].endswith('\n'):
                filtered_lines[-1] += '\n'

            # Add Include directive at the end
            filtered_lines.append(f'{include_line}\n')

            try:
                with open(config_path, 'w', encoding='utf-8') as handle:
                    handle.writelines(filtered_lines)
                Log.info(self, f'Added/moved Include directive to end of {config_path}')
            except OSError as error:
                Log.error(self, f'Failed to update {config_path}: {error}')

    def _provision_user(self, username: str, password: str) -> None:
        home_dir = f'/{username}'

        try:
            pwd.getpwnam(username)
            user_exists = True
        except KeyError:
            user_exists = False

        if not user_exists:
            # Create user with custom home directory using useradd
            command = ['useradd', '-m', '-d', home_dir, '-s', '/bin/bash', username]
            result = WOShellExec.cmd_exec(self, command, errormsg=f'useradd command failed for {username}')
            if not result:
                Log.error(self, f'Failed to create user {username}. Check debug logs for details.')
        else:
            Log.info(self, f'User {username} already exists, skipping creation.')

        # Set password
        if not WOShellExec.cmd_exec(self, ['passwd', username], input_data=f'{password}\n{password}\n', log=False):
            Log.error(self, f'Failed to set password for {username}')

        # Add user to wheel group
        if not WOShellExec.cmd_exec(self, ['usermod', '-aG', 'wheel', username]):
            Log.warn(self, "Could not add user to 'wheel' group. Ensure the group exists or adjust group membership manually.")

        # Get user info
        pw_record = pwd.getpwnam(username)
        ssh_dir = os.path.join(pw_record.pw_dir, '.ssh')
        auth_keys = os.path.join(ssh_dir, 'authorized_keys')
        bash_profile = os.path.join(pw_record.pw_dir, '.bash_profile')

        # Create .ssh directory and authorized_keys
        try:
            os.makedirs(ssh_dir, mode=0o700, exist_ok=True)
            with open(auth_keys, 'a', encoding='utf-8'):
                pass
            os.chmod(ssh_dir, 0o700)
            os.chmod(auth_keys, 0o600)
            os.chown(ssh_dir, pw_record.pw_uid, pw_record.pw_gid)
            os.chown(auth_keys, pw_record.pw_uid, pw_record.pw_gid)
        except OSError as error:
            Log.error(self, f'Failed to configure SSH directory for {username}: {error}')

        # Add sudo NOPASSWD to sudoers
        sudoers_line = f'{username}   ALL=(ALL)       NOPASSWD: ALL\n'
        sudoers_file = f'/etc/sudoers.d/90-{username}'
        try:
            with open(sudoers_file, 'w', encoding='utf-8') as handle:
                handle.write(sudoers_line)
            os.chmod(sudoers_file, 0o440)
            Log.info(self, f'Added NOPASSWD sudo access for {username}')
        except OSError as error:
            Log.warn(self, f'Failed to add sudo access for {username}: {error}')

        # Add "sudo -i" to .bash_profile to switch to root after login
        try:
            with open(bash_profile, 'a', encoding='utf-8') as handle:
                handle.write('\nsudo -i\n')
            os.chown(bash_profile, pw_record.pw_uid, pw_record.pw_gid)
            Log.info(self, f'Added auto-sudo to {username} .bash_profile')
        except OSError as error:
            Log.warn(self, f'Failed to update .bash_profile for {username}: {error}')

    def _render_sshd_config(self, username: str, port: str, allow_password: bool) -> None:
        sudo_user = os.getenv('SUDO_USER') or ''
        allowed_users = ' '.join(filter(None, dict.fromkeys([username, sudo_user]).keys()))
        if not allowed_users:
            allowed_users = username

        data = {
            'sshport': port,
            'authentication_methods': 'publickey,password' if allow_password else 'publickey',
            'password_auth': 'yes' if allow_password else 'no',
            'allow_users': allowed_users,
        }

        self._ensure_sshd_include()

        try:
            os.makedirs(SSH_DROPIN_DIR, exist_ok=True)
        except OSError as error:
            Log.error(self, f'Failed to ensure {SSH_DROPIN_DIR} exists: {error}')
            return

        WOTemplate.deploy(self, SSH_DROPIN_PATH, 'ssh.mustache', data, overwrite=True)
        if os.path.isdir('/etc/ssh'):
            WOGit.add(self, ['/etc/ssh'], msg='Updated SSH hardening settings')
        if not WOService.restart_service(self, 'ssh'):
            Log.error(self, 'service SSH restart failed.')


def load(app):
    app.handler.register(WOSecureController)
