# backend/src/db/repositories/base.py
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
