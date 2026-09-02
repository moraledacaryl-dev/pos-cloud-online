from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.settings import settings


def _sqlite_connect_args(url: str):
    return {'check_same_thread': False} if url.startswith('sqlite') else {}


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA foreign_keys=ON')
    cursor.close()


database_url = settings.resolved_database_url
connect_args = _sqlite_connect_args(database_url)
engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
if database_url.startswith('sqlite'):
    event.listen(engine, 'connect', _enable_sqlite_foreign_keys)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
