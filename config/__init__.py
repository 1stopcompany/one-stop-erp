"""One Stop ERP Django configuration package."""

# Django's mysql backend imports MySQLdb (mysqlclient) by name. mysqlclient is a C extension that
# needs a compiler at install time -- fine on the Windows dev machine and most VPS/dedicated hosts,
# but some shared hosting (e.g. cPanel accounts inside CageFS) denies execute permission on gcc, so
# it can never be installed there. Falling back to PyMySQL (pure Python, always installable, already
# a dependency -- see requirements.txt) registered under the MySQLdb name keeps Django's mysql
# backend working unchanged on hosts like that, without touching how it behaves anywhere mysqlclient
# already installs fine.
try:
    import MySQLdb  # noqa: F401
except ImportError:
    import pymysql
    pymysql.install_as_MySQLdb()

# Celery is optional during local development and automated checks. Keeping the
# import guarded prevents the whole Django project from failing to start when
# asynchronous-task dependencies are not installed yet.
try:
    from .celery import app as celery_app
except ModuleNotFoundError:
    celery_app = None

__all__ = ("celery_app",)
