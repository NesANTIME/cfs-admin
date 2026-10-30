"""chat videoconf contactos uid

Revision ID: c8f2a1b9d4e7
Revises: b7e3f91a2c05
Create Date: 2026-10-30 06:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f2a1b9d4e7'
down_revision: Union[str, None] = 'b7e3f91a2c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Columna uid_publico en empleados
    op.add_column(
        'empleados',
        sa.Column('uid_publico', sa.String(length=36), nullable=True),
    )
    # Llenar uid_publico para registros existentes si hay alguno
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id_empleado FROM empleados")).fetchall()
    for row in rows:
        conn.execute(
            sa.text("UPDATE empleados SET uid_publico = :uid WHERE id_empleado = :id"),
            {"uid": str(uuid.uuid4()), "id": row[0]},
        )
    # Hacerlo non-nullable y único
    op.alter_column('empleados', 'uid_publico', nullable=False)
    op.create_unique_constraint(op.f('uq_empleados_uid_publico'), 'empleados', ['uid_publico'])

    # 2. Columna id_sede en usuarios_sede
    op.add_column(
        'usuarios_sede',
        sa.Column('id_sede', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        op.f('fk_usuarios_sede_id_sede_sedes'),
        'usuarios_sede', 'sedes',
        ['id_sede'], ['id_sede'],
        ondelete='SET NULL',
    )

    # 3. Tabla contactos
    op.create_table(
        'contactos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('id_usuario', sa.Integer(), nullable=False),
        sa.Column('id_contacto', sa.Integer(), nullable=False),
        sa.Column('alias', sa.String(length=100), nullable=True),
        sa.Column('registrado_formalmente', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['id_usuario'], ['empleados.id_empleado'],
            name=op.f('fk_contactos_id_usuario_empleados'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_contacto'], ['empleados.id_empleado'],
            name=op.f('fk_contactos_id_contacto_empleados'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_contactos')),
        sa.UniqueConstraint('id_usuario', 'id_contacto', name=op.f('uq_contactos_usuario_contacto')),
    )
    op.create_index(op.f('ix_contactos_id_usuario'), 'contactos', ['id_usuario'], unique=False)
    op.create_index(op.f('ix_contactos_id_contacto'), 'contactos', ['id_contacto'], unique=False)

    # 4. Tabla mensajes_chat
    op.create_table(
        'mensajes_chat',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('id_remitente', sa.Integer(), nullable=False),
        sa.Column('id_destinatario', sa.Integer(), nullable=False),
        sa.Column('id_sede', sa.Integer(), nullable=False),
        sa.Column('contenido', sa.Text(), nullable=False),
        sa.Column('leido', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['id_remitente'], ['empleados.id_empleado'],
            name=op.f('fk_mensajes_chat_id_remitente_empleados'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_destinatario'], ['empleados.id_empleado'],
            name=op.f('fk_mensajes_chat_id_destinatario_empleados'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_sede'], ['sedes.id_sede'],
            name=op.f('fk_mensajes_chat_id_sede_sedes'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_mensajes_chat')),
    )
    op.create_index(op.f('ix_mensajes_chat_id_remitente'), 'mensajes_chat', ['id_remitente'], unique=False)
    op.create_index(op.f('ix_mensajes_chat_id_destinatario'), 'mensajes_chat', ['id_destinatario'], unique=False)
    op.create_index(op.f('ix_mensajes_chat_id_sede'), 'mensajes_chat', ['id_sede'], unique=False)
    op.create_index(op.f('ix_mensajes_chat_leido'), 'mensajes_chat', ['leido'], unique=False)
    op.create_index(op.f('ix_mensajes_chat_creado_en'), 'mensajes_chat', ['creado_en'], unique=False)

    # 5. Tabla salas_videoconf
    op.create_table(
        'salas_videoconf',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo_sala', sa.String(length=64), nullable=False),
        sa.Column('id_sede', sa.Integer(), nullable=False),
        sa.Column('id_iniciador', sa.Integer(), nullable=False),
        sa.Column('id_invitado', sa.Integer(), nullable=True),
        sa.Column('activa', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('creada_en', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ['id_sede'], ['sedes.id_sede'],
            name=op.f('fk_salas_videoconf_id_sede_sedes'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_iniciador'], ['empleados.id_empleado'],
            name=op.f('fk_salas_videoconf_id_iniciador_empleados'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['id_invitado'], ['empleados.id_empleado'],
            name=op.f('fk_salas_videoconf_id_invitado_empleados'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_salas_videoconf')),
        sa.UniqueConstraint('codigo_sala', name=op.f('uq_salas_videoconf_codigo_sala')),
    )
    op.create_index(op.f('ix_salas_videoconf_codigo_sala'), 'salas_videoconf', ['codigo_sala'], unique=True)
    op.create_index(op.f('ix_salas_videoconf_id_sede'), 'salas_videoconf', ['id_sede'], unique=False)
    op.create_index(op.f('ix_salas_videoconf_id_iniciador'), 'salas_videoconf', ['id_iniciador'], unique=False)


def downgrade() -> None:
    op.drop_table('salas_videoconf')
    op.drop_table('mensajes_chat')
    op.drop_table('contactos')
    op.drop_constraint(op.f('fk_usuarios_sede_id_sede_sedes'), 'usuarios_sede', type_='foreignkey')
    op.drop_column('usuarios_sede', 'id_sede')
    op.drop_constraint(op.f('uq_empleados_uid_publico'), 'empleados', type_='unique')
    op.drop_column('empleados', 'uid_publico')
