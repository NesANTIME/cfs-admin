"""agregar descripcion a sedes

Revision ID: 4e2a87b91f03
Revises: 26d4103a93c8
Create Date: 2026-10-27 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e2a87b91f03'
down_revision: Union[str, None] = '26d4103a93c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sedes', sa.Column('descripcion', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('sedes', 'descripcion')
