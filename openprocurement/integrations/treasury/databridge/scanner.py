# -*- coding: utf-8 -*-
import logging.config

from gevent import monkey, sleep, spawn
from gevent.event import Event
from retrying import retry

from datetime import datetime

from openprocurement.integrations.treasury.databridge.base_worker import BaseWorker
from openprocurement.integrations.treasury.databridge.constants import retry_multi


monkey.patch_all()

logger = logging.getLogger(__name__)


class Scanner(BaseWorker):
    def __init__(self, services_not_available, sleep_change_value, delay=15):
        super(Scanner, self).__init__(services_not_available)

        self.start_time = datetime.now()
        self.delay = delay

        self.initialization_event = Event()
        self.sleep_change_value = sleep_change_value

    @retry(stop_max_attempt_number=5, wait_exponential_multiplier=retry_multi)
    def initialize_sync(self, params=None, direction=None):
        if direction == 'backward':
            self.initialization_event.clear()
            assert params['descending']

            self.initialization_event.set()
            logger.info('Initial sync point {}'.format(self.initial_sync_point))

            return
        else:
            assert 'descending' not in params
            self.initialization_event.wait()
            params['offset'] = self.initial_sync_point['forward_offset']
            logger.info('Starting forward sync from offset {}'.format(params['offset']))

            return

    def get_contracts(self, params=None, direction=None):
        logging.info('GET CONTRACTS...')
        if params is None:
            params = dict()

        if direction is None:
            direction = str()


