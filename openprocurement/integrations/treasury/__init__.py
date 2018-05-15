# -*- coding: utf-8 -*-

"""
Main entry point
"""

import argparse
import os
import logging
import logging.config

from yaml import load

from openprocurement.integrations.treasury.databridge.bridge import ContractingDataBridge


logger = logging.getLogger('openprocurement.integrations.treasury.databridge')


def main(*args, **settings):
    parser = argparse.ArgumentParser(description='Contracting Data Bridge')
    parser.add_argument('config', type=str, help='Path to configuration file')
    parser.add_argument('--tender', type=str, help='Tender id to sync', dest='tender_id')
    params = parser.parse_args()

    if os.path.isfile(params.config):
        with open(params.config) as config_file_obj:
            config = load(config_file_obj.read())
        logging.config.dictConfig(config)

        if params.tender_id:
            ContractingDataBridge(config).sync_single_tender(params.tender_id)
        else:
            ContractingDataBridge(config).launch()
    else:
        logger.info('Invalid configuration file. Exiting...')


if __name__ == "__main__":
    main()

