"""agregar tipo mensaje chat

Revision ID: e2f3a4b5c6d7
Revises: d9e4a2c1b8f5
Create Date: 2026-11-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd9e4a2c1b8f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'mensajes_chat',
        sa.Column('tipo', sa.String(length=20), server_default='texto', nullable=False),
    )
    op.create_index(
        op.f('ix_contactos_id_usuario_formal'),
        'contactos',
        ['id_usuario', 'registrado_formalmente'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_contactos_id_usuario_formal'), table_name='contactos')
    op.drop_column('mensajes_chat', 'tipo')
