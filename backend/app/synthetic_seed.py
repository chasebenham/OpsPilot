"""Provision a new, migrated, otherwise empty dedicated synthetic database."""
from sqlalchemy import inspect, select, text
from .models import DATABASE_URL, engine, SessionLocal, Request, User, Department
from .synthetic_dataset import MARKER
from . import seed

def main():
    # This command is launched with DATABASE_URL set to the synthetic DB. Avoid
    # treating that value as the primary when validating the dedicated name.
    from sqlalchemy.engine import make_url
    url=make_url(DATABASE_URL)
    if url.get_backend_name()!='postgresql' or url.host not in ('localhost','127.0.0.1','::1') or not url.database or not url.database.endswith('_synthetic'):
        raise SystemExit('Refusing: DATABASE_URL must name a separate local *_synthetic PostgreSQL database.')
    if 'synthetic_dataset_marker' in inspect(engine).get_table_names():
        with engine.connect() as c:
            if c.execute(text('SELECT dataset_version FROM synthetic_dataset_marker')).scalar_one_or_none()==MARKER:
                print('Synthetic dataset already initialized; no changes made.'); return
        raise SystemExit('An unrecognized dataset marker exists; no changes made.')
    with SessionLocal() as db:
        if any(db.scalar(select(model.id).limit(1)) is not None for model in (Request,User,Department)):
            raise SystemExit('Database contains data without a trusted marker; refusing to relabel it.')
    seed.seed()
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE synthetic_dataset_marker (dataset_version VARCHAR(100) PRIMARY KEY)'))
        conn.execute(text('INSERT INTO synthetic_dataset_marker (dataset_version) VALUES (:version)'),{'version':MARKER})
    print('Created isolated fictional Meridian dataset.')

if __name__=='__main__': main()
