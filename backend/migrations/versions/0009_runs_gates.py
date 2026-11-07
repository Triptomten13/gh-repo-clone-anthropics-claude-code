"""DAEMON OBSERVABILITY (runs, run_events) and EVALUATION LAB release gates (release_gates, gate_runs).

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('runs',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('kind', sa.String(length=24), nullable=False),
                    sa.Column('ref', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('parent_id', sa.Integer(), nullable=True),
                    sa.Column('workflow', sa.String(length=96), nullable=False, server_default=''),
                    sa.Column('agent_id', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('user_email', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('status', sa.String(length=24), nullable=False),
                    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('input', sa.JSON(), nullable=True),
                    sa.Column('output', sa.JSON(), nullable=True),
                    sa.Column('error', sa.Text(), nullable=False, server_default=''),
                    sa.Column('tokens_in', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('tokens_out', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
                    sa.Column('policy_version', sa.String(length=32), nullable=False, server_default=''))
    for c in ('kind', 'ref', 'parent_id', 'agent_id', 'user_email', 'status', 'started_at'):
        op.create_index(f'ix_runs_{c}', 'runs', [c])
    op.create_table('run_events',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('run_id', sa.Integer(), nullable=False),
                    sa.Column('seq', sa.Integer(), nullable=False),
                    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('type', sa.String(length=24), nullable=False),
                    sa.Column('name', sa.String(length=160), nullable=False, server_default=''),
                    sa.Column('data', sa.JSON(), nullable=True),
                    sa.Column('duration_ms', sa.Integer(), nullable=True))
    op.create_index('ix_run_events_run_id', 'run_events', ['run_id'])
    op.create_table('release_gates',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('target_kind', sa.String(length=24), nullable=False),
                    sa.Column('suite', sa.String(length=64), nullable=False),
                    sa.Column('min_score', sa.Float(), nullable=False),
                    sa.Column('mandatory', sa.Boolean(), nullable=False),
                    sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
                    sa.Column('created_by', sa.String(length=255), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_release_gates_target_kind', 'release_gates', ['target_kind'])
    op.create_table('gate_runs',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('target_kind', sa.String(length=24), nullable=False),
                    sa.Column('target_ref', sa.String(length=160), nullable=False),
                    sa.Column('results', sa.JSON(), nullable=True),
                    sa.Column('passed', sa.Boolean(), nullable=False),
                    sa.Column('blocking', sa.JSON(), nullable=True),
                    sa.Column('created_by', sa.String(length=255), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_gate_runs_target_kind', 'gate_runs', ['target_kind'])
    op.create_index('ix_gate_runs_created_at', 'gate_runs', ['created_at'])


def downgrade() -> None:
    op.drop_table('gate_runs')
    op.drop_table('release_gates')
    op.drop_table('run_events')
    op.drop_table('runs')
