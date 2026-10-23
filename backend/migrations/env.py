from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Permite importar config/, db/ y core/ al ejecutar Alembic desde backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.config import MountUrlDb  # noqa: E402
from db.template.base import Base  # noqa: E402
import db.template  # noqa: E402,F401  (registra todos los modelos)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = MountUrlDb().render_as_string(hide_password = False)

# ConfigParser interpola "%", así que se escapa al fijar la opción.
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

target_metadata = Base.metadata

COMPARE = {
    "compare_type": True,
    "compare_server_default": True,
}


def run_migrations_offline() -> None:
    context.configure(
        url = url,
        target_metadata = target_metadata,
        literal_binds = True,
        dialect_opts = {"paramstyle": "named"},
        **COMPARE,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix = "sqlalchemy.",
        poolclass = pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection = connection,
            target_metadata = target_metadata,
            **COMPARE,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
