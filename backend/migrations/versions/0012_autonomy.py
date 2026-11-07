"""Model Hunter, Model Championship, Devil's Advocate, Account Vault: model_candidates, championships, critiques,
service_accounts.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('model_candidates',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('repo', sa.String(length=200), nullable=False),
                    sa.Column('file', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('revision', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('task', sa.String(length=48), nullable=False, server_default='general'),
                    sa.Column('license', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('commercial_use', sa.String(length=24), nullable=False, server_default='unknown'),
                    sa.Column('gated', sa.Boolean(), nullable=False, server_default=sa.false()),
                    sa.Column('size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
                    sa.Column('sha256', sa.String(length=64), nullable=False, server_default=''),
                    sa.Column('parameters_b', sa.Float(), nullable=True),
                    sa.Column('quantization', sa.String(length=24), nullable=False, server_default=''),
                    sa.Column('base_model', sa.String(length=200), nullable=False, server_default=''),
                    sa.Column('tags', sa.JSON(), nullable=True),
                    sa.Column('downloads', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('likes', sa.Integer(), nullable=False, server_default='0'),
                    sa.Column('last_modified', sa.String(length=40), nullable=False, server_default=''),
                    sa.Column('status', sa.String(length=24), nullable=False, server_default='discovered'),
                    sa.Column('reasons', sa.JSON(), nullable=True),
                    sa.Column('fit', sa.JSON(), nullable=True),
                    sa.Column('local_key', sa.String(length=96), nullable=False, server_default=''),
                    sa.Column('critique_id', sa.Integer(), nullable=True),
                    sa.Column('approval_id', sa.Integer(), nullable=True),
                    sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
                    sa.UniqueConstraint('repo', 'file', name='uq_model_candidates_repo_file'))
    op.create_index('ix_model_candidates_repo', 'model_candidates', ['repo'])
    op.create_index('ix_model_candidates_task', 'model_candidates', ['task'])
    op.create_index('ix_model_candidates_status', 'model_candidates', ['status'])

    op.create_table('championships',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('status', sa.String(length=16), nullable=False, server_default='running'),
                    sa.Column('created_by', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('hardware', sa.JSON(), nullable=True),
                    sa.Column('suites', sa.JSON(), nullable=True),
                    sa.Column('participants', sa.JSON(), nullable=True),
                    sa.Column('results', sa.JSON(), nullable=True),
                    sa.Column('standings', sa.JSON(), nullable=True),
                    sa.Column('deltas', sa.JSON(), nullable=True),
                    sa.Column('summary', sa.Text(), nullable=False, server_default=''),
                    sa.Column('error', sa.Text(), nullable=False, server_default=''))

    op.create_table('critiques',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('subject_kind', sa.String(length=32), nullable=False),
                    sa.Column('subject_ref', sa.String(length=96), nullable=False, server_default=''),
                    sa.Column('summary', sa.Text(), nullable=False, server_default=''),
                    sa.Column('mode', sa.String(length=24), nullable=False, server_default='DEVILS_ADVOCATE'),
                    sa.Column('verdict', sa.String(length=16), nullable=False, server_default='sound'),
                    sa.Column('findings', sa.JSON(), nullable=True),
                    sa.Column('checks', sa.JSON(), nullable=True),
                    sa.Column('reviewer', sa.String(length=160), nullable=False, server_default='rules'),
                    sa.Column('proposer', sa.String(length=160), nullable=False, server_default=''),
                    sa.Column('independent', sa.Boolean(), nullable=False, server_default=sa.true()),
                    sa.Column('status', sa.String(length=16), nullable=False, server_default='open'),
                    sa.Column('response', sa.Text(), nullable=False, server_default=''),
                    sa.Column('created_by', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_critiques_subject_kind', 'critiques', ['subject_kind'])
    op.create_index('ix_critiques_subject_ref', 'critiques', ['subject_ref'])
    op.create_index('ix_critiques_created_at', 'critiques', ['created_at'])

    op.create_table('service_accounts',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('service', sa.String(length=48), nullable=False),
                    sa.Column('identity', sa.String(length=128), nullable=False, server_default=''),
                    sa.Column('purpose', sa.Text(), nullable=False, server_default=''),
                    sa.Column('level', sa.Integer(), nullable=False, server_default='1'),
                    sa.Column('status', sa.String(length=24), nullable=False, server_default='proposed'),
                    sa.Column('scopes', sa.JSON(), nullable=True),
                    sa.Column('justification', sa.JSON(), nullable=True),
                    sa.Column('credential_id', sa.Integer(), nullable=True),
                    sa.Column('credential_scope', sa.String(length=96), nullable=False, server_default=''),
                    sa.Column('requested_by', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('approval_id', sa.Integer(), nullable=True),
                    sa.Column('critique_id', sa.Integer(), nullable=True),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('last_health_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('health', sa.JSON(), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
                    sa.Column('revoked_by', sa.String(length=255), nullable=False, server_default=''))
    op.create_index('ix_service_accounts_service', 'service_accounts', ['service'])
    op.create_index('ix_service_accounts_status', 'service_accounts', ['status'])


def downgrade() -> None:
    op.drop_index('ix_service_accounts_status', table_name='service_accounts')
    op.drop_index('ix_service_accounts_service', table_name='service_accounts')
    op.drop_table('service_accounts')
    op.drop_index('ix_critiques_created_at', table_name='critiques')
    op.drop_index('ix_critiques_subject_ref', table_name='critiques')
    op.drop_index('ix_critiques_subject_kind', table_name='critiques')
    op.drop_table('critiques')
    op.drop_table('championships')
    op.drop_index('ix_model_candidates_status', table_name='model_candidates')
    op.drop_index('ix_model_candidates_task', table_name='model_candidates')
    op.drop_index('ix_model_candidates_repo', table_name='model_candidates')
    op.drop_table('model_candidates')
