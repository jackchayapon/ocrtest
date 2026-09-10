from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.config import BACKEND_ROOT, Settings


class Database:
    def __init__(self, settings: Settings):
        url = settings.sqlalchemy_url
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False}
            if url.startswith("sqlite")
            else {"connect_timeout": 10},
            hide_parameters=True,
        )
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def set_pragmas(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self):
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
