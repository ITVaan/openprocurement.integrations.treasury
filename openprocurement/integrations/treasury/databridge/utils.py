# -*- coding: utf-8 -*-
from uuid import uuid4


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
