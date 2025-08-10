import json
import subprocess
from types import SimpleNamespace
from pathlib import Path

from wo.cli.main import WOTestApp
from wo.cli.plugins.site_backup import WOSiteBackupController


def test_backup_creates_expected_structure(tmp_path, monkeypatch):
    site_name = 'bktest.com'
    slug = site_name.replace('.', '-')
    site_path = tmp_path / 'site'
    htdocs = site_path / 'htdocs'
    htdocs.mkdir(parents=True)
    (htdocs / 'index.html').write_text('hello')
    (htdocs / 'wp-config.php').write_text('cfg')

    acl_dir = Path(f'/etc/nginx/acl/{slug}')
    acl_dir.mkdir(parents=True, exist_ok=True)
    (acl_dir / 'credentials').write_text('user:pass')

    siteinfo = SimpleNamespace(
        id=1,
        sitename=site_name,
        site_type='html',
        cache_type='basic',
        site_path=str(site_path),
        created_on=None,
        is_enabled=True,
        is_ssl=False,
        storage_fs='ext4',
        storage_db='mysql',
        db_name=None,
        db_user=None,
        db_password=None,
        db_host='localhost',
        is_hhvm=False,
        php_version='8.1',
    )

    from wo.cli.plugins import site_backup as site_backup_mod
    monkeypatch.setattr(site_backup_mod, 'getSiteInfo', lambda self, site: siteinfo)
    monkeypatch.setattr(site_backup_mod, '_timestamp', lambda: '2024-01-01_000000')

    backup_root = tmp_path / 'backups'
    with WOTestApp(argv=[]) as app:
        controller = WOSiteBackupController()
        controller.app = app
        controller._backup_site(site_name, backup_root=str(backup_root))

    archive = backup_root / site_name / '2024-01-01_000000.tar.zst'
    assert archive.is_file()
    backup_dir = backup_root / site_name / '2024-01-01_000000'
    assert not backup_dir.exists()

    extract_dir = tmp_path / 'extract'
    extract_dir.mkdir()
    subprocess.run(
        ["tar", "--zstd", "-xf", str(archive), "-C", str(extract_dir)],
        check=True,
    )
    extracted = extract_dir / '2024-01-01_000000'
    assert (extracted / 'htdocs' / 'index.html').is_file()
    assert (extracted / 'wp-config.php').is_file()
    meta = json.loads((extracted / 'vhost.json').read_text())
    assert meta['httpauth_user'] == 'user'
    assert meta['httpauth_pass'] == 'pass'


def test_cli_backup_all(monkeypatch):
    sites = [SimpleNamespace(sitename='a.com'), SimpleNamespace(sitename='b.com')]
    called = []
    from wo.cli.plugins import site_backup as site_backup_mod
    monkeypatch.setattr(site_backup_mod, 'getAllsites', lambda self: sites)

    def fake_backup(self, site, backup_root=None, backup_db=True, backup_files=True):
        called.append(site)

    monkeypatch.setattr(site_backup_mod.WOSiteBackupController, '_backup_site', fake_backup)

    with WOTestApp(argv=[]) as app:
        controller = WOSiteBackupController()
        controller.app = app
        controller.app._parsed_args = SimpleNamespace(all=True, site_name=None, db=False, files=False, path=None)
        controller.default()

    assert set(called) == {'a.com', 'b.com'}
