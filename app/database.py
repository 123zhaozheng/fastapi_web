from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

# PostgreSQL database engine
# Convert DATABASE_URI to string to avoid PostgresDsn object handling issues
database_uri = str(settings.DATABASE_URI) if settings.DATABASE_URI else None
if not database_uri:
    raise ValueError("DATABASE_URI is not set or is invalid")

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Attempting to create database engine with URI: {database_uri}")
engine = create_engine(database_uri)
logger.info("Database engine created successfully.")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()



def get_db():
    """
    Dependency function to get a new SQLAlchemy session for each request
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
