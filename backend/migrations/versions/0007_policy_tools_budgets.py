"""DAEMON CONTROL PLANE: policy rules (versioned), approval lifecycle, tool grants + invocations, budget rules.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('approvals') as b:
        b.add_column(sa.Column('category', sa.Integer(), nullable=False, server_default='3'))
        b.add_column(sa.Column('on_behalf_of', sa.String(length=255), nullable=False, server_default=''))
        b.add_column(sa.Column('payload_hash', sa.String(length=64), nullable=False, server_default=''))
        b.add_column(sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('delegated_to', sa.String(length=255), nullable=False, server_default=''))
        b.add_column(sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('revoked_by', sa.String(length=255), nullable=False, server_default=''))
        b.add_column(sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table('policy_rules',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('key', sa.String(length=96), nullable=False),
                    sa.Column('version', sa.Integer(), nullable=False),
                    sa.Column('action', sa.String(length=128), nullable=False),
                    sa.Column('category', sa.Integer(), nullable=False),
                    sa.Column('conditions', sa.JSON(), nullable=False),
                    sa.Column('priority', sa.Integer(), nullable=False),
                    sa.Column('reason', sa.Text(), nullable=False),
                    sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
                    sa.Column('created_by', sa.String(length=255), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_policy_rules_key', 'policy_rules', ['key'])
    op.create_index('ix_policy_rules_action', 'policy_rules', ['action'])
    op.create_index('ix_policy_rules_superseded_at', 'policy_rules', ['superseded_at'])
    op.create_table('tool_grants',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('subject_kind', sa.String(length=16), nullable=False),
                    sa.Column('subject_id', sa.String(length=96), nullable=False),
                    sa.Column('tool', sa.String(length=96), nullable=False),
                    sa.Column('operations', sa.JSON(), nullable=False),
                    sa.Column('environments', sa.JSON(), nullable=False),
                    sa.Column('max_calls_per_day', sa.Integer(), nullable=True),
                    sa.Column('credential_scope', sa.String(length=96), nullable=False, server_default=''),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
                    sa.Column('reason', sa.Text(), nullable=False),
                    sa.Column('created_by', sa.String(length=255), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    for c in ('subject_kind', 'subject_id', 'tool'):
        op.create_index(f'ix_tool_grants_{c}', 'tool_grants', [c])
    op.create_table('tool_invocations',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('tool', sa.String(length=96), nullable=False),
                    sa.Column('operation', sa.String(length=16), nullable=False),
                    sa.Column('agent_id', sa.String(length=64), nullable=False),
                    sa.Column('user_email', sa.String(length=255), nullable=False),
                    sa.Column('workflow', sa.String(length=96), nullable=False),
                    sa.Column('run_id', sa.Integer(), nullable=True),
                    sa.Column('grant_id', sa.Integer(), nullable=True),
                    sa.Column('decision', sa.String(length=24), nullable=False),
                    sa.Column('category', sa.Integer(), nullable=False),
                    sa.Column('reason', sa.Text(), nullable=False),
                    sa.Column('status', sa.String(length=24), nullable=False),
                    sa.Column('args_redacted', sa.JSON(), nullable=False),
                    sa.Column('output_summary', sa.Text(), nullable=False),
                    sa.Column('approval_id', sa.Integer(), nullable=True),
                    sa.Column('latency_ms', sa.Integer(), nullable=False))
    for c in ('created_at', 'tool', 'agent_id', 'user_email', 'run_id'):
        op.create_index(f'ix_tool_invocations_{c}', 'tool_invocations', [c])
    op.create_table('budget_rules',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('scope_kind', sa.String(length=16), nullable=False),
                    sa.Column('scope_id', sa.String(length=96), nullable=False),
                    sa.Column('metric', sa.String(length=24), nullable=False),
                    sa.Column('period', sa.String(length=8), nullable=False),
                    sa.Column('limit', sa.Float(), nullable=False),
                    sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
                    sa.Column('created_by', sa.String(length=255), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_budget_rules_scope_kind', 'budget_rules', ['scope_kind'])
    op.create_table('usage_counters',
                    sa.Column('key', sa.String(length=160), primary_key=True),
                    sa.Column('day', sa.String(length=10), primary_key=True),
                    sa.Column('used', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_table('usage_counters')
    op.drop_table('budget_rules')
    op.drop_table('tool_invocations')
    op.drop_table('tool_grants')
    op.drop_table('policy_rules')
    with op.batch_alter_table('approvals') as b:
        for c in ('consumed_at', 'revoked_by', 'revoked_at', 'delegated_to', 'expires_at', 'payload_hash', 'on_behalf_of', 'category'):
            b.drop_column(c)
