import mysql.connector
from mysql.connector import pooling
from contextlib import contextmanager
from ajustes import get_config

# Crie o pool uma vez, na importação do módulo
_config = get_config()
_pool = pooling.MySQLConnectionPool(pool_name="mypool", pool_size=5, **_config)

@contextmanager
def get_connection():
    conn = _pool.get_connection()
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