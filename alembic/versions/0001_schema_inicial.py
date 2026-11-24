"""schema inicial

Revision ID: 0001
Revises:
Create Date: 2026-11-24 02:25:03.665179

Cria as tabelas empresa, linha e viagem com suas constraints e índices.
Complementos manuais (não detectados pelo autogenerate):
  - sequence viagem_codigo_seq: gera o número do id_viagem (VG0181...);
  - função + trigger que atualizam viagem.updated_at em todo UPDATE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FUNCAO_UPDATED_AT = """
CREATE FUNCTION fn_atualizar_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

TRIGGER_UPDATED_AT = """
CREATE TRIGGER trg_viagem_updated_at
    BEFORE UPDATE ON viagem
    FOR EACH ROW EXECUTE FUNCTION fn_atualizar_updated_at()
"""


def upgrade() -> None:
    """Cria o schema inicial."""
    # Manual: sequence exclusiva do identificador de negócio (independente dos SERIAL).
    op.execute("CREATE SEQUENCE viagem_codigo_seq")

    # --- gerado pelo autogenerate (revisado) ---
    op.create_table('empresa',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=3), nullable=False),
    sa.Column('nome', sa.String(length=100), nullable=False),
    sa.CheckConstraint("codigo ~ '^[0-9]{3}$'", name=op.f('ck_empresa_codigo_formato')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_empresa')),
    sa.UniqueConstraint('codigo', name=op.f('uq_empresa_codigo'))
    )
    op.create_table('linha',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('empresa_id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=10), nullable=False),
    sa.Column('descricao', sa.String(length=120), nullable=False),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresa.id'], name=op.f('fk_linha_empresa_id_empresa'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_linha')),
    sa.UniqueConstraint('empresa_id', 'codigo', name=op.f('uq_linha_empresa_id_codigo'))
    )
    op.create_table('viagem',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('id_viagem', sa.String(length=20), nullable=False),
    sa.Column('linha_id', sa.Integer(), nullable=False),
    sa.Column('data_viagem', sa.Date(), nullable=False),
    sa.Column('horario_programado', sa.Time(), nullable=False),
    sa.Column('veiculo', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=13), nullable=False),
    sa.Column('motivo_nao_realizacao', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'REALIZADA' AND motivo_nao_realizacao IS NULL) OR (status = 'NAO_REALIZADA' AND motivo_nao_realizacao IS NOT NULL)", name=op.f('ck_viagem_status_motivo_coerente')),
    sa.CheckConstraint("id_viagem ~ '^VG[0-9]{4,}$'", name=op.f('ck_viagem_id_viagem_formato')),
    sa.CheckConstraint("motivo_nao_realizacao IN ('MANUTENCAO', 'PESSOAL', 'TRANSITO', 'OPERACAO')", name=op.f('ck_viagem_motivo_valido')),
    sa.CheckConstraint("status IN ('REALIZADA', 'NAO_REALIZADA')", name=op.f('ck_viagem_status_valido')),
    sa.ForeignKeyConstraint(['linha_id'], ['linha.id'], name=op.f('fk_viagem_linha_id_linha'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_viagem')),
    sa.UniqueConstraint('id_viagem', name=op.f('uq_viagem_id_viagem'))
    )
    op.create_index(op.f('ix_viagem_data_viagem'), 'viagem', ['data_viagem'], unique=False)
    op.create_index(op.f('ix_viagem_linha_id'), 'viagem', ['linha_id'], unique=False)
    # --- fim do trecho gerado ---

    # Manual: updated_at atualizado pelo banco em qualquer UPDATE da tabela viagem.
    op.execute(FUNCAO_UPDATED_AT)
    op.execute(TRIGGER_UPDATED_AT)


def downgrade() -> None:
    """Remove o schema inicial (ordem inversa do upgrade)."""
    # Manual: trigger e função antes da tabela.
    op.execute("DROP TRIGGER trg_viagem_updated_at ON viagem")
    op.execute("DROP FUNCTION fn_atualizar_updated_at()")

    # --- gerado pelo autogenerate (revisado) ---
    op.drop_index(op.f('ix_viagem_linha_id'), table_name='viagem')
    op.drop_index(op.f('ix_viagem_data_viagem'), table_name='viagem')
    op.drop_table('viagem')
    op.drop_table('linha')
    op.drop_table('empresa')
    # --- fim do trecho gerado ---

    # Manual: sequence por último.
    op.execute("DROP SEQUENCE viagem_codigo_seq")
