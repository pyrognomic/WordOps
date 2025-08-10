import json
from types import SimpleNamespace
from pathlib import Path

from wo.cli.main import WOTestApp
from wo.cli.plugins.site_backup import WOSiteBackupController
from wo.core.variables import WOVar


def test_backup_includes_vhost_and_credentials(tmp_path, monkeypatch):
    site_name = 'bktest.com'
    slug = site_name.replace('.', '-')
    site_path = tmp_path / 'site'
    htdocs = site_path / 'htdocs'
    htdocs.mkdir(parents=True)
    (htdocs / 'index.html').write_text('hello')

    sa_dir = Path('/etc/nginx/sites-available')
    sa_dir.mkdir(parents=True, exist_ok=True)
    (sa_dir / site_name).write_text('vhost config')

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

    monkeypatch.setattr(WOVar, 'wo_date', '01Jan2024-00-00-00')
    from wo.cli.plugins import site_backup as site_backup_mod
    monkeypatch.setattr(site_backup_mod, 'getSiteInfo', lambda self, site: siteinfo)

    with WOTestApp(argv=[]) as app:
        controller = WOSiteBackupController()
        controller.app = app
        controller._backup_site(site_name)

    backup_dir = site_path / 'backup' / '01Jan2024-00-00-00'
    assert (backup_dir / site_name).is_file()
    assert (backup_dir / 'credentials').is_file()
    meta = json.loads((backup_dir / 'vhost.json').read_text())
    assert meta['httpauth_user'] == 'user'
    assert meta['httpauth_pass'] == 'pass'
