from pathlib import Path

from wo.cli.main import WOTestApp
from wo.cli.plugins.site_clone import WOSiteCloneController
from wo.core.acme import WOAcme
from wo.core.sslutils import SSL
from wo.core.services import WOService
from wo.core.git import WOGit
import wo.cli.plugins.site_clone as site_clone


def test_copy_acl_rewrites_slug(tmp_path):
    base = tmp_path
    src_slug = 'source-com'
    dest_slug = 'dest-com'
    src_dir = base / src_slug
    src_dir.mkdir(parents=True)
    (src_dir / 'protected.conf').write_text(
        'auth_basic_user_file /etc/nginx/acl/source-com/credentials;\n'
        'fastcgi_pass unix:/run/php/php84-fpm-source-com.sock;'
    )
    (src_dir / 'credentials').write_text('user:pass')
    # simulate pre-existing destination directory rendered by setupdomain
    dest_dir = base / dest_slug
    dest_dir.mkdir(parents=True)
    (dest_dir / 'protected.conf').write_text('placeholder')
    with WOTestApp(argv=[]) as app:
        controller = WOSiteCloneController()
        controller.app = app
        controller._copy_acl(src_slug, dest_slug, base=str(base))
    assert dest_dir.is_dir()
    content = (dest_dir / 'protected.conf').read_text()
    assert 'source-com' not in content
    assert 'dest-com' in content
    assert (dest_dir / 'credentials').is_file()


def test_setup_letsencrypt(monkeypatch, tmp_path):
    calls = {}

    def fake_setupletsencrypt(self, domains, data):
        calls['domains'] = domains
        return True

    def fake_deploycert(self, domain):
        calls['deploy'] = domain

    def fake_httpsredirect(self, domain, domains, redirect=True):
        calls['redirect'] = (domain, domains, redirect)

    def fake_siteurlhttps(self, domain):
        calls['siteurl'] = domain

    def fake_reload(self, service):
        calls['reload'] = service
        return True

    def fake_git(self, paths, msg=""):
        calls['git'] = (paths, msg)

    def fake_update(self, domain, **kwargs):
        calls['update'] = (domain, kwargs)

    monkeypatch.setattr(WOAcme, 'setupletsencrypt', fake_setupletsencrypt)
    monkeypatch.setattr(WOAcme, 'deploycert', fake_deploycert)
    monkeypatch.setattr(SSL, 'httpsredirect', fake_httpsredirect)
    monkeypatch.setattr(SSL, 'siteurlhttps', fake_siteurlhttps)
    monkeypatch.setattr(WOService, 'reload_service', fake_reload)
    monkeypatch.setattr(WOGit, 'add', fake_git)
    monkeypatch.setattr(site_clone, 'updateSiteInfo', fake_update)

    with WOTestApp(argv=[]) as app:
        controller = WOSiteCloneController()
        controller.app = app
        controller._setup_letsencrypt('example.com', str(tmp_path))

    assert calls['domains'] == ['example.com', 'www.example.com']
    assert calls['deploy'] == 'example.com'
    assert calls['redirect'][0] == 'example.com'
    assert calls['update'][0] == 'example.com'
    assert calls['update'][1]['ssl'] is True
