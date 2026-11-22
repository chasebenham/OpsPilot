"""Read-only access to an explicitly provisioned, isolated local demo database."""
import os
from functools import lru_cache
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from .models import DATABASE_URL

MARKER = 'meridian-synthetic-v1'

def validate_url(url):
    candidate=make_url(url)
    primary=make_url(DATABASE_URL)
    if (candidate.get_backend_name()!='postgresql' or candidate.host not in ('localhost','127.0.0.1','::1')
        or not candidate.database or not candidate.database.endswith('_synthetic') or candidate.database==primary.database):
        raise ValueError('Synthetic analytics requires a separate local PostgreSQL database ending in _synthetic.')

@lru_cache(maxsize=2)
def engine_for(url):
    validate_url(url)
    return create_engine(url, pool_pre_ping=True)

def open_dataset():
    url=os.getenv('SYNTHETIC_DATABASE_URL','').strip()
    if not url: raise ValueError('Synthetic dataset is not configured. See README setup instructions.')
    engine=engine_for(url)
    # Server-side read-only transaction protects the isolated dataset from this endpoint.
    session=Session(engine)
    try:
        session.execute(text('SET TRANSACTION READ ONLY'))
        marker=session.execute(text('SELECT dataset_version FROM synthetic_dataset_marker')).scalar_one_or_none()
        if marker!=MARKER: raise ValueError('The synthetic dataset marker is missing or invalid.')
        return session
    except Exception:
        session.close()
        raise
