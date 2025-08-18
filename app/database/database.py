from sqlalchemy import create_engine, MetaData, text  # <- importar text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from .config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.debug
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
metadata = MetaData()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version();"))  # <- aquí
            version = result.fetchone()[0]
            logger.info(f"✅ Conexión exitosa a PostgreSQL: {version}")
            return True
    except SQLAlchemyError as e:
        logger.error(f"❌ Error probando la conexión: {e}")
        return False

def create_tables():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tablas creadas exitosamente")
    except SQLAlchemyError as e:
        logger.error(f"❌ Error creando las tablas: {e}")
        raise
