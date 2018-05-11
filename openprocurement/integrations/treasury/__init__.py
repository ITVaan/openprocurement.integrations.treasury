# -*- coding: utf-8 -*-

"""
Main entry point
"""

if 'test' not in __import__('sys').argv[0]:
    import gevent.monkey
    gevent.monkey.patch_all()

from logging import getLogger

from openprocurement.integrations.treasury.databridge.bridge import DataBridge


LOGGER = getLogger("{}.init".format(__name__))

def main(global_config, **settings):
    from pyramid.config import Configurator

    from pyramid.authentication import BasicAuthAuthenticationPolicy
    from pyramid.authorization import ACLAuthorizationPolicy
    from pyramid.config import Configurator
    from pyramid.events import NewRequest, ContextFound
    from pyramid.renderers import JSON, JSONP

    LOGGER.info('Run data bridge...')

