from wo.utils import test
from wo.cli.main import WOTestApp
from unittest.mock import patch


class CliTestCaseStackPurge(test.WOTestCase):

    def test_wo_cli_stack_purge_web(self):
        with WOTestApp(
                argv=['stack', 'purge', '--web', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_admin(self):
        with WOTestApp(
                argv=['stack', 'purge', '--admin', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_nginx(self):
        with WOTestApp(
                argv=['stack', 'purge', '--nginx', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_php(self):
        with WOTestApp(argv=['stack', 'purge',
                                      '--php', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_mysql(self):
        with WOTestApp(argv=['stack', 'purge',
                                      '--mysql', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_wpcli(self):
        with WOTestApp(argv=['stack', 'purge',
                                      '--wpcli', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_phpmyadmin(self):
        with WOTestApp(
                argv=['stack', 'purge', '--phpmyadmin', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_adminer(self):
        with WOTestApp(
                argv=['stack', 'purge', '--adminer', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_utils(self):
        with WOTestApp(argv=['stack', 'purge',
                                      '--utils', '--force']) as app:
            app.run()

    def test_wo_cli_stack_purge_all_removes_php(self):
        def fake_is_installed(self, package_name):
            return package_name == 'php7.4-fpm'

        with patch('wo.core.aptget.WOAptGet.is_installed',
                   new=fake_is_installed), \
             patch('wo.core.aptget.WOAptGet.remove') as mock_remove, \
             patch('wo.core.aptget.WOAptGet.auto_remove'):
            with WOTestApp(argv=['stack', 'purge', '--all', '--force']) as app:
                app.run()

        removed = mock_remove.call_args[0][1]
        assert 'php7.4-fpm' in removed
