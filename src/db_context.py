import mysql.connector
from contextlib import contextmanager
from ajustes import get_config

@contextmanager
def get_connection():
    config = get_config()
    conn = mysql.connector.connect(**config)
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
