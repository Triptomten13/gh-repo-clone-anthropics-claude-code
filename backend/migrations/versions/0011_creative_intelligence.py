"""DAEMON CREATIVE INTELLIGENCE: creative_tournaments, creative_entries, model_profiles.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('creative_tournaments',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('created_by', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('agent_id', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('workflow', sa.String(length=96), nullable=False, server_default=''),
                    sa.Column('brief', sa.Text(), nullable=False),
                    sa.Column('category', sa.String(length=32), nullable=False, server_default='general'),
                    sa.Column('language', sa.String(length=8), nullable=False, server_default='en'),
                    sa.Column('routing_mode', sa.String(length=24), nullable=False, server_default='FREE_FIRST'),
                    sa.Column('strategy', sa.String(length=24), nullable=False, server_default='AUTOMATIC'),
                    sa.Column('status', sa.String(length=24), nullable=False, server_default='running'),
                    sa.Column('quality_target', sa.Float(), nullable=False, server_default='0.7'),
                    sa.Column('budget', sa.JSON(), nullable=True),
                    sa.Column('usage', sa.JSON(), nullable=True),
                    sa.Column('plan', sa.JSON(), nullable=True),
                    sa.Column('stop_reason', sa.Text(), nullable=False, server_default=''),
                    sa.Column('result_entry_id', sa.Integer(), nullable=True),
                    sa.Column('final_score', sa.Float(), nullable=True),
                    sa.Column('alternatives', sa.JSON(), nullable=True),
                    sa.Column('classification', sa.String(length=24), nullable=False, server_default='INTERNAL'),
                    sa.Column('cache_key', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('trace_run_id', sa.Integer(), nullable=True),
                    sa.Column('approval_id', sa.Integer(), nullable=True),
                    sa.Column('saved_document_id', sa.Integer(), nullable=True))
    for c in ('created_at', 'created_by', 'category', 'status', 'cache_key'):
        op.create_index(f'ix_creative_tournaments_{c}', 'creative_tournaments', [c])
    op.create_table('creative_entries',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('tournament_id', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('round', sa.Integer(), nullable=False, server_default='1'),
                    sa.Column('role', sa.String(length=16), nullable=False, server_default='candidate'),
                    sa.Column('model_id', sa.String(length=160), nullable=False, server_default=''),
                    sa.Column('provider', sa.String(length=48), nullable=False, server_default=''),
                    sa.Column('model_version', sa.String(length=80), nullable=False, server_default=''),
                    sa.Column('status', sa.String(length=16), nullable=False, server_default='ok'),
                    sa.Column('error', sa.Text(), nullable=False, server_default=''),
                    sa.Column('text', sa.Text(), nullable=False, server_default=''),
                    sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
                    sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('deterministic', sa.JSON(), nullable=True),
                    sa.Column('critiques', sa.JSON(), nullable=True),
                    sa.Column('score', sa.Float(), nullable=True),
                    sa.Column('sources', sa.JSON(), nullable=True),
                    sa.Column('prompt_hash', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('accepted', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_creative_entries_tournament_id', 'creative_entries', ['tournament_id'])
    op.create_table('model_profiles',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('model_id', sa.String(length=160), nullable=False),
                    sa.Column('model_version', sa.String(length=80), nullable=False, server_default=''),
                    sa.Column('category', sa.String(length=32), nullable=False),
                    sa.Column('score', sa.Float(), nullable=False, server_default='0'),
                    sa.Column('metrics', sa.JSON(), nullable=True),
                    sa.Column('tasks', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('conditions', sa.JSON(), nullable=True),
                    sa.Column('source', sa.String(length=24), nullable=False, server_default='benchmark'),
                    sa.Column('measured_at', sa.DateTime(timezone=True), nullable=False))
    for c in ('model_id', 'category', 'measured_at'):
        op.create_index(f'ix_model_profiles_{c}', 'model_profiles', [c])


def downgrade() -> None:
    op.drop_table('model_profiles')
    op.drop_table('creative_entries')
    op.drop_table('creative_tournaments')
