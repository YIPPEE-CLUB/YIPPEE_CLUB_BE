"""Shared targets for manual isolated-instance setup tools."""
if __package__:
    from .setup_mysql_dev import admin_sql as _admin_sql
else:
    from setup_mysql_dev import admin_sql as _admin_sql

DATABASES = ("test_yippee_migration_legacy", "test_yippee_migration_fresh")
PORT = 33307
SERVER_ID = 9133307


def admin_sql(sql):
    identity = _admin_sql("SELECT @@server_id, @@port;\n", port=PORT)
    if identity != f"{SERVER_ID}\t{PORT}":
        raise RuntimeError("격리된 리허설 서버가 아닙니다. 변경 없이 중단합니다.")
    return _admin_sql(sql, port=PORT)
