import mysql.connector
from contextlib import contextmanager

DB_CONFIG = {
    'host': 'rodrigopirata.duckdns.org',
    'user': 'rodrigo',
    'password': 'Ro220199@mariadb',
    'database': 'Trabalho',
    'port': 3306
}

@contextmanager
def get_connection():
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_cursor(commit=False):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            yield cursor
            if commit:
                conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            cursor.close()
