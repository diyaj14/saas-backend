# backend/app/models/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    Every database table we create will inherit from this Base class.
    Alembic uses this to look for new tables and generate migrations!
    """
    pass
