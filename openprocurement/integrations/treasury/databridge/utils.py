# -*- coding: utf-8 -*-
import logging
import os

from uuid import uuid4
from datetime import datetime, timedelta

from decimal import Decimal
from pytz import timezone
from iso8601 import parse_date
from esculator.calculations import discount_rate_days, payments_days, calculate_payments

from openprocurement.integrations.treasury.databridge.journal_msg_ids import (
    DATABRIDGE_COPY_CONTRACT_ITEMS, DATABRIDGE_EXCEPTION, DATABRIDGE_MISSING_CONTRACT_ITEMS
)

TZ = timezone(os.environ['TZ'] if 'TZ' in os.environ else 'Europe/Kiev')
logger = logging.getLogger('openprocurement.integrations.treasury.databridge')


def generate_request_id():
    return b'data-bridge-req-' + str(uuid4()).encode('ascii')


def journal_context(record=None, params=None):
    if params is None:
        params = {}

    if record is None:
        record = {}

    for k, v in params.items():
        record['JOURNAL_' + k] = v
    return record


class CacheDB(object):
    def __init__(self, config):
        self.config = config

        self._backend = None
        self._db_name = None
        self._port = None
        self._host = None

        if 'cache_host' in self.config:
            import redis

            self._backend = 'redis'
            self._host = self.config.get('cache_host')
            self._port = self.config.get('cache_port') or 6379
            self._db_name = self.config.get('cache_db_name') or 0
            self.db = redis.StrictRedis(
                host=self._host, port=self._port, db=self._db_name
            )
            self.set_value = self.db.set
            self.has_value = self.db.exists
        else:
            from lazydb import Db

            self._backend = "lazydb"
            self._db_name = self.config.get('cache_db_name') or 'databridge_cache_db'
            self.db = Db(self._db_name)
            self.set_value = self.db.put
            self.has_value = self.db.has

    def get(self, key):
        return self.db.get(key)

    def put(self, key, value):
        self.set_value(key, value)

    def has(self, key):
        return self.has_value(key)


def to_decimal(fraction):
    return str(Decimal(fraction.numerator) / Decimal(fraction.denominator))


def generate_milestones(contract, tender):
    days_per_year = 365
    npv_calculation_duration = 20
    announcement_date = parse_date(tender['noticePublicationDate'])

    if not 'period' in contract:
        contract_days = timedelta(days=contract['value']['contractDuration']['days'])
        contract_years = contract['value']['contractDuration']['years']

        contract_end_date = announcement_date.replace(
            year=announcement_date.year + contract_years, hour=0, minute=0,
            second=0, microsecond=0
        ) + contract_days

        contract['period'] = {'startDate': contract['dateSigned'], 'endDate': contract_end_date.isoformat()}

    # set contract.period.startDate to contract.dateSigned if missed
    if 'startDate' not in contract['period']:
        contract['period']['startDate'] = contract['dateSigned']

    contract_start_date = parse_date(contract['period']['startDate'])
    contract_end_date = parse_date(contract['period']['endDate'])

    contract_duration_years = contract['value']['contractDuration']['years']
    contract_duration_days = contract['value']['contractDuration']['days']
    yearly_payments_percentage = contract['value']['yearlyPaymentsPercentage']
    annual_cost_reduction = contract['value']['annualCostsReduction']

    days_for_discount_rate = discount_rate_days(announcement_date, days_per_year, npv_calculation_duration)
    days_with_payments = payments_days(
        contract_duration_years, contract_duration_days, days_for_discount_rate, days_per_year,
        npv_calculation_duration
    )

    payments = calculate_payments(
        yearly_payments_percentage, annual_cost_reduction, days_with_payments, days_for_discount_rate
    )

    milestones = []
    years_before_contract_start = contract_start_date.year - announcement_date.year

    last_milestone_sequence_number = 16 + years_before_contract_start

    logger.info('Generate milestones for esco tender {}'.format(tender['id']))

    # def to_decimal(fraction):
    #     return str(Decimal(fraction.numerator) / Decimal(fraction.denominator))

    for sequence_number in xrange(1, last_milestone_sequence_number + 1):
        date_modified = datetime.now(TZ)
        milestone = {
            'id': uuid4().hex,
            'sequenceNumber': sequence_number,
            'date': date_modified.isoformat(),
            'dateModified': date_modified.isoformat(),
            'amountPaid': {
                'amount': 0,
                'currency': contract['value']['currency'],
                'valueAddedTaxIncluded': contract['value']['valueAddedTaxIncluded']
            },
            'value': {
                'amount': to_decimal(payments[sequence_number - 1]) if sequence_number <= 21 else 0.00,
                'currency': contract['value']['currency'],
                'valueAddedTaxIncluded': contract['value']['valueAddedTaxIncluded']
            },
        }

        if sequence_number == 1:
            milestone_start_date = announcement_date
            milestone_end_date = TZ.localize(datetime(announcement_date.year + sequence_number, 1, 1))
            milestone['status'] = 'pending'
        elif sequence_number == last_milestone_sequence_number:
            milestone_start_date = TZ.localize(datetime(announcement_date.year + sequence_number - 1, 1, 1))
            milestone_end_date = TZ.localize(datetime(
                announcement_date.year + sequence_number - 1, contract_start_date.month, contract_start_date.day))
        else:
            milestone_start_date = TZ.localize(datetime(announcement_date.year + sequence_number - 1, 1, 1))
            milestone_end_date = TZ.localize(datetime(announcement_date.year + sequence_number, 1, 1))

        if contract_end_date.year >= milestone_start_date.year and sequence_number != 1:
            milestone['status'] = 'scheduled'
        elif contract_end_date.year < milestone_start_date.year:
            milestone['status'] = 'spare'

        if contract_end_date.year == announcement_date.year + sequence_number - 1:
            milestone_end_date = TZ.localize(datetime(
                announcement_date.year + sequence_number - 1, contract_end_date.month, contract_end_date.day))

        milestone['period'] = {
            'startDate': milestone_start_date.isoformat(), 'endDate': milestone_end_date.isoformat()
        }

        title = 'Milestone #{} of year {}'.format(sequence_number, milestone_start_date.year)

        milestone['title'] = title
        milestone['description'] = title
        milestones.append(milestone)

    return milestones


def fill_base_contract_data(contract, tender):
    contract['tender_id'] = tender['id']
    contract['procuringEntity'] = tender['procuringEntity']

    # Set contract mode
    if tender.get('mode'):
        contract['mode'] = tender['mode']

    # Copy items from tender
    if not contract.get('items'):
        logger.info(
            'Copying contract {} items'.format(contract['id']),
            extra=journal_context(
                {'MESSAGE_ID': DATABRIDGE_COPY_CONTRACT_ITEMS},
                {'CONTRACT_ID': contract['id'], 'TENDER_ID': tender['id']}
            )
        )
        if tender.get('lots'):
            related_awards = [aw for aw in tender['awards'] if aw['id'] == contract['awardID']]

            if related_awards:
                award = related_awards[0]

                if award.get("items"):
                    logger.debug('Copying items from related award {}'.format(award['id']))
                    contract['items'] = award['items']
                else:
                    logger.debug('Copying items matching related lot {}'.format(award['lotID']))
                    contract['items'] = [item for item in tender['items'] if item.get('relatedLot') == award['lotID']]
            else:
                logger.warn(
                    'Not found related award for contact {} of tender {}'.format(contract['id'], tender['id']),
                    extra=journal_context(
                        {'MESSAGE_ID': DATABRIDGE_EXCEPTION},
                        params={'CONTRACT_ID': contract['id'], 'TENDER_ID': tender['id']}
                    )
                )
        else:
            logger.debug(
                'Copying all tender {} items into contract {}'.format(tender['id'], contract['id']),
                extra=journal_context(
                    {'MESSAGE_ID': DATABRIDGE_COPY_CONTRACT_ITEMS},
                    params={'CONTRACT_ID': contract['id'], 'TENDER_ID': tender['id']}
                )
            )
            contract['items'] = tender['items']

    # delete `items` key if contract.items is empty list
    if isinstance(contract.get('items', None), list) and len(contract.get('items')) == 0:
        logger.info(
            "Clearing 'items' key for contract with empty 'items' list",
            extra=journal_context(
                {'MESSAGE_ID': DATABRIDGE_COPY_CONTRACT_ITEMS},
                {'CONTRACT_ID': contract['id'], 'TENDER_ID': tender['id']}
            )
        )

        del contract['items']

    if not contract.get('items'):
        logger.warn(
            'Contract {} of tender {} does not contain items info'.format(contract['id'], tender['id']),
            extra=journal_context(
                {'MESSAGE_ID': DATABRIDGE_MISSING_CONTRACT_ITEMS},
                {'CONTRACT_ID': contract['id'], 'TENDER_ID': tender['id']}
            )
        )

    for item in contract.get('items', []):
        conditions = [
            'deliveryDate' in item, item['deliveryDate'].get('startDate'), item['deliveryDate'].get('endDate')
        ]

        if all(conditions):
            if item['deliveryDate']['startDate'] > item['deliveryDate']['endDate']:
                logger.info(
                    'Found dates missmatch {} and {}'.format(
                        item['deliveryDate']['startDate'], item['deliveryDate']['endDate']
                    ),
                    extra=journal_context(
                        {'MESSAGE_ID': DATABRIDGE_EXCEPTION},
                        params={'CONTRACT_ID': contract['id'], 'TENDER_ID': tender['id']}
                    )
                )

                del item['deliveryDate']['startDate']

                logger.info(
                    'startDate value cleaned.',
                    extra=journal_context(
                        {'MESSAGE_ID': DATABRIDGE_EXCEPTION},
                        params={'CONTRACT_ID': contract['id'], 'TENDER_ID': tender['id']}
                    )
                )


def handle_common_tenders(contract, tender):
    contract['contractType'] = 'common'
    logger.info('Handle common tender {}'.format(tender['id']), extra={'MESSAGE_ID': 'handle_common_tenders'})


def handle_esco_tenders(contract, tender):
    contract['contractType'] = 'esco'
    logger.info('Handle esco tender {}'.format(tender['id']), extra={'MESSAGE_ID': 'handle_esco_tenders'})

    keys = ['NBUdiscountRate', 'noticePublicationDate']
    keys_from_lot = ['fundingKind', 'yearlyPaymentsPercentageRange', 'minValue']

    # Fill contract values from lot
    if tender.get('lots'):
        related_awards = [aw for aw in tender['awards'] if aw['id'] == contract['awardID']]

        if related_awards:
            lot_id = related_awards[0]['lotID']
            related_lots = [lot for lot in tender['lots'] if lot['id'] == lot_id]

            if related_lots:
                logger.debug('Fill contract {} values from lot {}'.format(contract['id'], related_lots[0]['id']))

                for key in keys_from_lot:
                    contract[key] = related_lots[0][key]
            else:
                logger.critical(
                    'Not found related lot for contract {} of tender {}'.format(contract['id'], tender['id']),
                    extra={'MESSAGE_ID': 'not_found_related_lot'}
                )

                keys += keys_from_lot
        else:
            logger.warn('Not found related award for contract {} of tender {}'.format(contract['id'], tender['id']))
            keys += keys_from_lot
    else:
        keys += keys_from_lot

    for key in keys:
        contract[key] = tender[key]

    contract['milestones'] = generate_milestones(contract, tender)
