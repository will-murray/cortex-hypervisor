"""
Cross-cutting infrastructure used by every domain:
    db.py     — SQLAlchemy engine + session factory (Cloud SQL)
    orm.py    — SQLAlchemy declarative models
    secrets.py — Google Secret Manager client
"""
