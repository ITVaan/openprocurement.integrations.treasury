# -*- coding: utf-8 -*-
import logging.config
import gevent

from gevent import monkey, Greenlet

from openprocurement.integrations.treasury.databridge.utils import journal_context
from openprocurement.integrations.treasury.databridge.journal_msg_ids import DATABRIDGE_START_UPLOAD


monkey.patch_all()


logger = logging.getLogger(__name__)


class BaseWorker(Greenlet):
    def __init__(self, services_not_available, delay=15):
        super(BaseWorker, self).__init__()
        self.services_not_available = services_not_available
        self.exit = False
        self.delay = delay

    def _start_jobs(self):
        raise NotImplementedError

    def _run(self):
        self.services_not_available.wait()
        logger.info(
            'Start {} worker'.format(type(self).__name__),
            extra=journal_context({'MESSAGE_ID': DATABRIDGE_START_UPLOAD}, {})
        )

        self.immortal_jobs = self._start_jobs()

        try:
            while not self.exit:
                gevent.sleep(self.delay)
                self.check_and_revive_jobs()
        except Exception as e:
            logger.error(e)
            gevent.killall(self.immortal_jobs.values(), timeout=5)

    def revive_job(self, name):
        logger.warning(
            '{} dead try restart'.format(name),
            extra=journal_context({'MESSAGE_ID': 'DATABRIDGE_RESTART_{}'.format(name.lower())}, {})
        )
        self.immortal_jobs.get[name] = gevent.spawn(getattr(self, name))
        logger.info('Worker {} complete his job.'.format(type(self).__name__))

    def check_and_revive_jobs(self):
        for name, job in self.immortal_jobs.items():
            if job.dead:
                self.revive_job(name)

    def shutdown(self):
        self.exit = True
        logger.info('Worker {} complete his job.'.format(type(self).__name__))



