"""uid dispositivos y logs auditoria

Revision ID: 1a2b3c4d5e6f
Revises: f3b4c5d6e7a8
Create Date: 2026-11-18 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Columnas nuevas para dispositivos_red
    op.add_column('dispositivos_red', sa.Column('descripcion', sa.Text(), nullable=True))
    op.add_column('dispositivos_red', sa.Column('uid_dispositivo', sa.String(length=128), nullable=True))
    op.add_column('dispositivos_red', sa.Column('contrasena_hash', sa.String(length=255), nullable=True))
    op.add_column('dispositivos_red', sa.Column('vinculado', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('dispositivos_red', sa.Column('ultimo_ping', sa.DateTime(timezone=True), nullable=True))
    op.add_column('dispositivos_red', sa.Column('detalles_hardware', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_dispositivos_red_uid_dispositivo', 'dispositivos_red', ['uid_dispositivo'])

    # 2. Tabla logs_auditoria
    op.create_table(
        'logs_auditoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('accion', sa.String(length=100), nullable=False),
        sa.Column('entidad', sa.String(length=50), nullable=False),
        sa.Column('id_entidad', sa.Integer(), nullable=True),
        sa.Column('detalle', sa.Text(), nullable=True),
        sa.Column('id_actor', sa.Integer(), nullable=True),
        sa.Column('actor_usuario', sa.String(length=50), nullable=True),
        sa.Column('ip_origen', sa.String(length=45), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['id_actor'], ['empleados.id_empleado'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_logs_auditoria_accion', 'logs_auditoria', ['accion'])
    op.create_index('ix_logs_auditoria_entidad', 'logs_auditoria', ['entidad'])
    op.create_index('ix_logs_auditoria_actor_usuario', 'logs_auditoria', ['actor_usuario'])
    op.create_index('ix_logs_auditoria_creado_en', 'logs_auditoria', ['creado_en'])
    op.create_index('ix_logs_accion_creado_en', 'logs_auditoria', ['accion', 'creado_en'])
    op.create_index('ix_logs_entidad_creado_en', 'logs_auditoria', ['entidad', 'creado_en'])


def downgrade() -> None:
    op.drop_index('ix_logs_entidad_creado_en', table_name='logs_auditoria')
    op.drop_index('ix_logs_accion_creado_en', table_name='logs_auditoria')
    op.drop_index('ix_logs_auditoria_creado_en', table_name='logs_auditoria')
    op.drop_index('ix_logs_auditoria_actor_usuario', table_name='logs_auditoria')
    op.drop_index('ix_logs_auditoria_entidad', table_name='logs_auditoria')
    op.drop_index('ix_logs_auditoria_accion', table_name='logs_auditoria')
    op.drop_table('logs_auditoria')

    op.drop_constraint('uq_dispositivos_red_uid_dispositivo', 'dispositivos_red', type_='unique')
    op.drop_column('dispositivos_red', 'detalles_hardware')
    op.drop_column('dispositivos_red', 'ultimo_ping')
    op.drop_column('dispositivos_red', 'vinculado')
    op.drop_column('dispositivos_red', 'contrasena_hash')
    op.drop_column('dispositivos_red', 'uid_dispositivo')
    op.drop_column('dispositivos_red', 'descripcion')
