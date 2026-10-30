"""agregar presencia empleado

Revision ID: b7e3f91a2c05
Revises: a1b2c3d4e5f6
Create Date: 2026-10-30 05:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e3f91a2c05'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'empleados',
        sa.Column('en_linea', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'empleados',
        sa.Column('ultima_vez_en_linea', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('empleados', 'ultima_vez_en_linea')
    op.drop_column('empleados', 'en_linea')
