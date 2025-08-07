from wo.utils import test
from wo.cli.main import WOTestApp
from unittest.mock import patch
import os


class CliTestCaseStackRemove(test.WOTestCase):

    def test_wo_cli_stack_remove_admin(self):
        with WOTestApp(argv=['stack', 'remove', '--admin', '--force']) as app:
            app.run()

    def test_wo_cli_stack_remove_nginx(self):
        with WOTestApp(argv=['stack', 'remove', '--nginx', '--force']) as app:
            app.run()

    def test_wo_cli_stack_remove_php(self):
        with WOTestApp(argv=['stack', 'remove', '--php', '--force']) as app:
            app.run()

    def test_wo_cli_stack_remove_mysql(self):
        with WOTestApp(argv=['stack', 'remove', '--mysql', '--force']) as app:
            app.run()

    def test_wo_cli_stack_remove_wpcli(self):
        orig_isfile = os.path.isfile

        def fake_isfile(path):
            if path in ['/usr/local/bin/wp', '/usr/bin/wp']:
                return True
            return orig_isfile(path)

        def fake_is_installed(self, package_name):
            return package_name == 'wp-cli'

        with patch('os.path.isfile', side_effect=fake_isfile), \
             patch('wo.core.aptget.WOAptGet.is_installed',
                   side_effect=fake_is_installed), \
             patch('wo.core.aptget.WOAptGet.remove') as mock_remove, \
             patch('wo.core.aptget.WOAptGet.auto_remove'), \
             patch('wo.core.fileutils.WOFileUtils.remove') as mock_file_remove:
            with WOTestApp(argv=['stack', 'remove', '--wpcli', '--force']) as app:
                app.run()

        removed_pkgs = mock_remove.call_args[0][1]
        removed_files = mock_file_remove.call_args[0][1]
        assert 'wp-cli' in removed_pkgs
        assert '/usr/local/bin/wp' in removed_files
        assert '/usr/bin/wp' in removed_files

    def test_wo_cli_stack_remove_phpmyadmin(self):
        with WOTestApp(argv=['stack', 'remove',
                                      '--phpmyadmin', '--force']) as app:
            app.run()

    def test_wo_cli_stack_remove_adminer(self):
        with WOTestApp(
                argv=['stack', 'remove', '--adminer', '--force']) as app:
            app.run()

    def test_wo_cli_stack_remove_utils(self):
        with WOTestApp(argv=['stack', 'remove', '--utils', '--force']) as app:
            app.run()
