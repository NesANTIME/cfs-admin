"""agregar invitaciones videoconferencia

Revision ID: a4b5c6d7e8f9
Revises: f3b4c5d6e7a8
Create Date: 2026-11-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = 'f3b4c5d6e7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'invitaciones_videoconf',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('id_sala', sa.Integer(), nullable=False),
        sa.Column('id_invitador', sa.Integer(), nullable=False),
        sa.Column('id_invitado', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=20), server_default='pendiente', nullable=False),
        sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expira_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('respondida_en', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            'id_invitador <> id_invitado',
            name=op.f('ck_invitaciones_videoconf_invitacion_no_auto'),
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente','aceptada','rechazada','cancelada','expirada','finalizada')",
            name=op.f('ck_invitaciones_videoconf_invitacion_estado_valido'),
        ),
        sa.ForeignKeyConstraint(
            ['id_sala'], ['salas_videoconf.id'],
            name=op.f('fk_invitaciones_videoconf_id_sala_salas_videoconf'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_invitador'], ['empleados.id_empleado'],
            name=op.f('fk_invitaciones_videoconf_id_invitador_empleados'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_invitado'], ['empleados.id_empleado'],
            name=op.f('fk_invitaciones_videoconf_id_invitado_empleados'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_invitaciones_videoconf')),
        sa.UniqueConstraint('id_sala', 'id_invitado', name='uq_invitaciones_sala_invitado'),
    )
    op.create_index(
        op.f('ix_invitaciones_videoconf_id_sala'),
        'invitaciones_videoconf',
        ['id_sala'],
        unique=False,
    )
    op.create_index(
        op.f('ix_invitaciones_videoconf_id_invitador'),
        'invitaciones_videoconf',
        ['id_invitador'],
        unique=False,
    )
    op.create_index(
        op.f('ix_invitaciones_videoconf_id_invitado'),
        'invitaciones_videoconf',
        ['id_invitado'],
        unique=False,
    )
    op.create_index(
        'ix_invitaciones_invitado_estado',
        'invitaciones_videoconf',
        ['id_invitado', 'estado'],
        unique=False,
    )
    op.create_index(
        'ix_invitaciones_invitador_estado',
        'invitaciones_videoconf',
        ['id_invitador', 'estado'],
        unique=False,
    )
    op.create_index(
        'uq_invitaciones_pendientes_par',
        'invitaciones_videoconf',
        ['id_invitador', 'id_invitado'],
        unique=True,
        postgresql_where=sa.text("estado = 'pendiente'"),
    )

    # Las salas antiguas no tenían invitación; no deben quedar accesibles.
    op.execute("UPDATE salas_videoconf SET activa = false WHERE activa = true")


def downgrade() -> None:
    op.drop_index('uq_invitaciones_pendientes_par', table_name='invitaciones_videoconf')
    op.drop_index('ix_invitaciones_invitador_estado', table_name='invitaciones_videoconf')
    op.drop_index('ix_invitaciones_invitado_estado', table_name='invitaciones_videoconf')
    op.drop_index(op.f('ix_invitaciones_videoconf_id_invitado'), table_name='invitaciones_videoconf')
    op.drop_index(op.f('ix_invitaciones_videoconf_id_invitador'), table_name='invitaciones_videoconf')
    op.drop_index(op.f('ix_invitaciones_videoconf_id_sala'), table_name='invitaciones_videoconf')
    op.drop_table('invitaciones_videoconf')
