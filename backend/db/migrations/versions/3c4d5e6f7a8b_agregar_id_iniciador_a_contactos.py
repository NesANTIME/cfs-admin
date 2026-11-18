"""agregar id_iniciador a contactos

Revision ID: 3c4d5e6f7a8b
Revises: 1a2b3c4d5e6f
Create Date: 2026-11-18 11:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c4d5e6f7a8b'
down_revision: Union[str, None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'contactos',
        sa.Column('id_iniciador', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_contactos_id_iniciador_empleados',
        'contactos',
        'empleados',
        ['id_iniciador'],
        ['id_empleado'],
        ondelete='SET NULL'
    )
    op.create_index(
        'ix_contactos_id_iniciador',
        'contactos',
        ['id_iniciador']
    )


def downgrade() -> None:
    op.drop_index('ix_contactos_id_iniciador', table_name='contactos')
    op.drop_constraint('fk_contactos_id_iniciador_empleados', 'contactos', type_='foreignkey')
    op.drop_column('contactos', 'id_iniciador')
