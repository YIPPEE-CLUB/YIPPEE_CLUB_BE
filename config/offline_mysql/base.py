from django.core.exceptions import ImproperlyConfigured
from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper


class DatabaseWrapper(MySQLDatabaseWrapper):
    def get_new_connection(self, conn_params):
        # Covers default, __no_db__, new threads and test-creation connections.
        raise ImproperlyConfigured("Offline User preview forbids all database connections.")
