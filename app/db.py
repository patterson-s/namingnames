import os
import psycopg
from psycopg.rows import dict_row


def get_conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["NAMINGNAMES_DB"], row_factory=dict_row)
