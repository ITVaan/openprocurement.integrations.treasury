# -*- coding: utf-8 -*-
import logging.config
import os
import argparse
import gevent

from functools import partial

from ConfigParser import SafeConfigParser

from gevent import monkey, event
from restkit import RequestError, ResourceError
from retrying import retry

from openprocurement.integrations.treasury.databridge.scanner import Scanner
from openprocurement.integrations.treasury.databridge.sleep_change_value import APIRateController
from openprocurement.integrations.treasury.databridge.utils import journal_context
from openprocurement.integrations.treasury.databridge.journal_msg_ids import (
    DATABRIDGE_START,
    DATABRIDGE_DOC_SERVICE_CONN_ERROR
)
from openprocurement.integrations.treasury.databridge.constants import retry_mult

monkey.patch_all()

logger = logging.getLogger(__name__)


class DataBridge(object):
    def __init__(self, config):
        super(DataBridge, self).__init__()
        self.config = config

        self.api_version = self.config_get('tenders_api_version')

        self.services_not_available = event.Event()

        self.delay = int(self.config_get('delay')) or 15
        self.increment_step = int(self.config_get('increment_step')) or 1
        self.decrement_step = int(self.config_get('decrement_step')) or 1
        self.sleep_change_value = APIRateController(self.increment_step, self.decrement_step)

        self.scanner = partial(
            Scanner.spawn,
            services_not_available=self.services_not_available,
            sleep_change_value=self.sleep_change_value,
            delay=self.delay
        )

    def config_get(self, name):
        return self.config.get('app:api', name)

    @retry(stop_max_attempt_number=5, wait_exponential_multiplier=retry_mult)
    def check_openprocurement_api(self):
        try:
            pass
        except (RequestError, ResourceError) as e:
            logger.info('Server connection error, message {}'.format(e),
                        extra=journal_context({"MESSAGE_ID": DATABRIDGE_DOC_SERVICE_CONN_ERROR}, {}))
            raise e
        else:
            return True

    def all_available(self):
        try:
            self.check_openprocurement_api()
        except Exception as e:
            logger.info("Service is unavailable, message {}".format(e))
            return False
        else:
            return True

    def run(self):
        logger.info('Start Data Bridge', extra=journal_context({"MESSAGE_ID": DATABRIDGE_START}, {}))

        counter = 0
        try:
            while True:
                gevent.sleep(self.delay)

                if counter == 5:
                    counter = 0
                counter += 1
        except KeyboardInterrupt:
            logger.info('Exiting...')
        except Exception as e:
            logger.error(e)

    def launch(self):
        while True:
            if self.all_available():
                self.run()
                break
            gevent.sleep(self.delay)


def main():
    logger.info('Run data bridge...')

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
        logger.info('Invalid configuration file. Exiting...')


if __name__ == '__main__':
    main()

