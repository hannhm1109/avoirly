from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_sessions(url):
    engine = create_engine(
        url, pool_pre_ping=True, connect_args={"connect_timeout": 10}, hide_parameters=True
    )
    return engine, sessionmaker(engine, expire_on_commit=False)
