# -*- coding: utf-8 -*-

"""
Main entry point
"""

import argparse
import os

if 'test' not in __import__('sys').argv[0]:
    import gevent.monkey
    gevent.monkey.patch_all()

import logging.config
from logging import getLogger
from ConfigParser import SafeConfigParser

from openprocurement.integrations.treasury.databridge.bridge import DataBridge


LOGGER = getLogger(__name__)


def main(*args, **settings):
    parser = argparse.ArgumentParser(description='Data Bridge')
    parser.add_argument('config', type=str, help='Path to configuration file')

    params = parser.parse_args()

    if os.path.isfile(params.config):
        config = SafeConfigParser()
        config.read(params.config)
        logging.config.fileConfig(params.config)
        bridge = DataBridge(config)
        bridge.launch()
    else:
        LOGGER.info('Invalid configuration file. Exiting...')

