import os

from wo.core.logging import Log
from wo.core.template import WOTemplate
from wo.core.variables import WOVar


class WOConf():
    """wo stack configuration utilities"""
    def __init__():
        pass

    def nginxcommon(self):
        """nginx common configuration deployment"""
        ngxcom = '/etc/nginx/common'
        if not os.path.exists(ngxcom):
            os.mkdir(ngxcom)
        Log.debug(self, 'deploying common nginx templates')
        data = dict(release=WOVar.wo_version)

        WOTemplate.deploy(self,
                          '{0}/php.conf'.format(ngxcom),
                          'php.mustache', data)

        WOTemplate.deploy(
            self, '{0}/redis.conf'.format(ngxcom),
            'redis.mustache', data)

        WOTemplate.deploy(
            self, '{0}/wp.conf'.format(ngxcom),
            'wp.mustache', data)

        WOTemplate.deploy(
            self, '{0}/wpfc.conf'.format(ngxcom),
            'wpfc.mustache', data)

        WOTemplate.deploy(
            self, '{0}/wpsc.conf'.format(ngxcom),
            'wpsc.mustache', data)

        WOTemplate.deploy(
            self, '{0}/wprocket.conf'.format(ngxcom),
            'wprocket.mustache', data)

        WOTemplate.deploy(
            self, '{0}/wpce.conf'.format(ngxcom),
            'wpce.mustache', data)
