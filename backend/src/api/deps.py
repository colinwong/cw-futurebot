from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session

# Re-export for convenience in route files
GetSession = Depends(get_session)
