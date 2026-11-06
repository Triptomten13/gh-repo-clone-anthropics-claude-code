"""DAEMON KNOWLEDGE VAULT: document classification, collection, explicit access; collections with inherited access.
Existing documents become INTERNAL / general / no explicit list — exactly the previous visibility.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('documents') as b:
        b.add_column(sa.Column('classification', sa.String(length=24), nullable=False, server_default='INTERNAL'))
        b.add_column(sa.Column('collection', sa.String(length=96), nullable=False, server_default='general'))
        b.add_column(sa.Column('access', sa.JSON(), nullable=True))
        b.create_index('ix_documents_classification', ['classification'])
        b.create_index('ix_documents_collection', ['collection'])
    op.create_table('collections',
                    sa.Column('name', sa.String(length=96), primary_key=True),
                    sa.Column('description', sa.Text(), nullable=False, server_default=''),
                    sa.Column('classification', sa.String(length=24), nullable=False, server_default='INTERNAL'),
                    sa.Column('access', sa.JSON(), nullable=True),
                    sa.Column('owner', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_table('collections')
    with op.batch_alter_table('documents') as b:
        b.drop_index('ix_documents_collection')
        b.drop_index('ix_documents_classification')
        b.drop_column('access')
        b.drop_column('collection')
        b.drop_column('classification')
