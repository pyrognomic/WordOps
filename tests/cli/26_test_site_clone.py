from pathlib import Path

from wo.cli.main import WOTestApp
from wo.cli.plugins.site_clone import WOSiteCloneController


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
