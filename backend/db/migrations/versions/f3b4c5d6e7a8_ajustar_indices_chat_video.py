"""ajustar indices chat video

Revision ID: f3b4c5d6e7a8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f3b4c5d6e7a8'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # El índice único sobre codigo_sala ya existe; el constraint adicional es redundante.
    op.execute(
        "ALTER TABLE salas_videoconf "
        "DROP CONSTRAINT IF EXISTS uq_salas_videoconf_codigo_sala"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_salas_videoconf_id_invitado "
        "ON salas_videoconf (id_invitado)"
    )
    # Asegura el índice compuesto en instalaciones donde e2f3 ya estaba aplicada.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contactos_id_usuario_formal "
        "ON contactos (id_usuario, registrado_formalmente)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_salas_videoconf_id_invitado")
    op.execute(
        "ALTER TABLE salas_videoconf "
        "ADD CONSTRAINT uq_salas_videoconf_codigo_sala UNIQUE (codigo_sala)"
    )
