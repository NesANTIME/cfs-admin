"""agregar servicios usuario

Revision ID: a1b2c3d4e5f6
Revises: 4e2a87b91f03
Create Date: 2026-10-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '4e2a87b91f03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'servicios_usuario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('id_empleado', sa.Integer(), nullable=False),
        sa.Column('tipo_servicio', sa.String(length=50), nullable=False),
        sa.Column('habilitado', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('id_sede', sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "tipo_servicio IN ('videoconferencia', 'chat')",
            name=op.f('ck_servicios_usuario_tipo_servicio_valido'),
        ),
        sa.ForeignKeyConstraint(
            ['id_empleado'],
            ['empleados.id_empleado'],
            name=op.f('fk_servicios_usuario_id_empleado_empleados'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_sede'],
            ['sedes.id_sede'],
            name=op.f('fk_servicios_usuario_id_sede_sedes'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_servicios_usuario')),
        sa.UniqueConstraint(
            'id_empleado',
            'tipo_servicio',
            name=op.f('uq_servicios_usuario_id_empleado_tipo_servicio'),
        ),
    )
    op.create_index(
        op.f('ix_servicios_usuario_id_empleado'),
        'servicios_usuario',
        ['id_empleado'],
        unique=False,
    )
    op.create_index(
        op.f('ix_servicios_usuario_id_sede'),
        'servicios_usuario',
        ['id_sede'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_servicios_usuario_id_sede'), table_name='servicios_usuario')
    op.drop_index(op.f('ix_servicios_usuario_id_empleado'), table_name='servicios_usuario')
    op.drop_table('servicios_usuario')
