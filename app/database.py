from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from redis import Redis

from app.config import settings

# PostgreSQL database engine
# Convert DATABASE_URI to string to avoid PostgresDsn object handling issues
database_uri = str(settings.DATABASE_URI) if settings.DATABASE_URI else None
if not database_uri:
    raise ValueError("DATABASE_URI is not set or is invalid")

engine = create_engine(database_uri)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Redis connection - handle gracefully if Redis is not available
try:
    redis_client = Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        db=settings.REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=5,  # Add a timeout to avoid long delays if Redis is not available
    )
    # Test connection
    redis_client.ping()
except Exception as e:
    import logging
    logging.warning(f"Redis connection failed: {str(e)}. Using dummy Redis client.")
    
    # Create a dummy Redis client for testing without Redis
    class DummyRedis:
        def __init__(self):
            self._data = {}
            
        def get(self, key):
            return self._data.get(key)
            
        def set(self, key, value):
            self._data[key] = value
            return True
            
        def ping(self):
            return True
            
        def info(self):
            return {"redis_version": "dummy"}
        
    redis_client = DummyRedis()


def get_db():
    """
    Dependency function to get a new SQLAlchemy session for each request
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
