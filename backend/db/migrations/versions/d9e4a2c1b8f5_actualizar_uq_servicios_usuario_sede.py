"""actualizar uq servicios usuario sede

Revision ID: d9e4a2c1b8f5
Revises: c8f2a1b9d4e7
Create Date: 2026-11-02 01:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e4a2c1b8f5'
down_revision: Union[str, None] = 'c8f2a1b9d4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        op.f('uq_servicios_usuario_id_empleado_tipo_servicio'),
        'servicios_usuario',
        type_='unique',
    )
    op.create_unique_constraint(
        op.f('uq_servicios_usuario_id_empleado_tipo_servicio_sede'),
        'servicios_usuario',
        ['id_empleado', 'tipo_servicio', 'id_sede'],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('uq_servicios_usuario_id_empleado_tipo_servicio_sede'),
        'servicios_usuario',
        type_='unique',
    )
    op.create_unique_constraint(
        op.f('uq_servicios_usuario_id_empleado_tipo_servicio'),
        'servicios_usuario',
        ['id_empleado', 'tipo_servicio'],
    )
