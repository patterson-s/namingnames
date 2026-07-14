#!/usr/bin/env python3

import psycopg
from psycopg.rows import dict_row
from config import config


def get_conn() -> psycopg.Connection:
    return psycopg.connect(config.NEON_CONN_STR, row_factory=dict_row)
