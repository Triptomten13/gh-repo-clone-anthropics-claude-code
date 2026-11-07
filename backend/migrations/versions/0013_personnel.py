"""Astral personnel: agent identity dimensions (race, specialisations, role, rank, department, supervisor, personality,
mission, skills, lifecycle, source, onboarding, version), and the Bestiary (species, specializations),
departments, agent relationships and agent versions.

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

AGENT_COLUMNS = [
    sa.Column('persona_name', sa.String(length=80), nullable=False, server_default=''),
    sa.Column('species_key', sa.String(length=64), nullable=False, server_default=''),
    sa.Column('specializations', sa.JSON(), nullable=True),
    sa.Column('title', sa.String(length=128), nullable=False, server_default=''),
    sa.Column('rank', sa.String(length=48), nullable=False, server_default='Specialist'),
    sa.Column('department_key', sa.String(length=64), nullable=False, server_default=''),
    sa.Column('supervisor_id', sa.String(length=64), nullable=True),
    sa.Column('alt_names', sa.JSON(), nullable=True),
    sa.Column('traits', sa.JSON(), nullable=True),
    sa.Column('personality', sa.Text(), nullable=False, server_default=''),
    sa.Column('communication_style', sa.JSON(), nullable=True),
    sa.Column('languages', sa.JSON(), nullable=True),
    sa.Column('purpose', sa.Text(), nullable=False, server_default=''),
    sa.Column('mission', sa.JSON(), nullable=True),
    sa.Column('skills', sa.JSON(), nullable=True),
    sa.Column('tool_suggestions', sa.JSON(), nullable=True),
    sa.Column('lifecycle', sa.String(length=24), nullable=False, server_default='ACTIVE'),
    sa.Column('source', sa.String(length=16), nullable=False, server_default='CODE'),
    sa.Column('custom', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('onboarding', sa.JSON(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
    sa.Column('created_by', sa.String(length=255), nullable=False, server_default='system'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
]


def upgrade() -> None:
    with op.batch_alter_table('agents') as b:
        for c in AGENT_COLUMNS:
            b.add_column(c.copy())
        b.create_index('ix_agents_species_key', ['species_key'])
        b.create_index('ix_agents_department_key', ['department_key'])
        b.create_index('ix_agents_lifecycle', ['lifecycle'])

    op.create_table('species',
                    sa.Column('key', sa.String(length=64), primary_key=True),
                    sa.Column('name', sa.String(length=96), nullable=False),
                    sa.Column('category', sa.String(length=32), nullable=False),
                    sa.Column('kind', sa.String(length=16), nullable=False, server_default='being'),
                    sa.Column('alt_names', sa.JSON(), nullable=True),
                    sa.Column('subtypes', sa.JSON(), nullable=True),
                    sa.Column('origin', sa.String(length=160), nullable=False, server_default=''),
                    sa.Column('folklore', sa.Text(), nullable=False, server_default=''),
                    sa.Column('fiction', sa.Text(), nullable=False, server_default=''),
                    sa.Column('canon', sa.Text(), nullable=False, server_default=''),
                    sa.Column('traits', sa.JSON(), nullable=True),
                    sa.Column('abilities', sa.JSON(), nullable=True),
                    sa.Column('strengths', sa.JSON(), nullable=True),
                    sa.Column('weaknesses', sa.JSON(), nullable=True),
                    sa.Column('symbolism', sa.Text(), nullable=False, server_default=''),
                    sa.Column('relations', sa.JSON(), nullable=True),
                    sa.Column('specializations', sa.JSON(), nullable=True),
                    sa.Column('example_roles', sa.JSON(), nullable=True),
                    sa.Column('sources', sa.JSON(), nullable=True),
                    sa.Column('caution', sa.Text(), nullable=False, server_default=''),
                    sa.Column('user_created', sa.Boolean(), nullable=False, server_default=sa.false()),
                    sa.Column('created_by', sa.String(length=255), nullable=False, server_default='system'),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_species_category', 'species', ['category'])
    op.create_table('specializations',
                    sa.Column('key', sa.String(length=64), primary_key=True),
                    sa.Column('name', sa.String(length=96), nullable=False),
                    sa.Column('description', sa.Text(), nullable=False, server_default=''),
                    sa.Column('competencies', sa.JSON(), nullable=True),
                    sa.Column('tools', sa.JSON(), nullable=True),
                    sa.Column('departments', sa.JSON(), nullable=True),
                    sa.Column('example_tasks', sa.JSON(), nullable=True),
                    sa.Column('keywords', sa.JSON(), nullable=True),
                    sa.Column('user_created', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('departments',
                    sa.Column('key', sa.String(length=64), primary_key=True),
                    sa.Column('name', sa.String(length=96), nullable=False),
                    sa.Column('description', sa.Text(), nullable=False, server_default=''),
                    sa.Column('manager_id', sa.String(length=64), nullable=True),
                    sa.Column('divisions', sa.JSON(), nullable=True))
    op.create_table('agent_relationships',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('source_agent_id', sa.String(length=64), nullable=False),
                    sa.Column('target_agent_id', sa.String(length=64), nullable=False),
                    sa.Column('relationship_type', sa.String(length=32), nullable=False),
                    sa.Column('description', sa.Text(), nullable=False, server_default=''))
    op.create_index('ix_agent_relationships_source_agent_id', 'agent_relationships', ['source_agent_id'])
    op.create_index('ix_agent_relationships_target_agent_id', 'agent_relationships', ['target_agent_id'])
    op.create_table('agent_versions',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('agent_id', sa.String(length=64), nullable=False),
                    sa.Column('version', sa.Integer(), nullable=False),
                    sa.Column('snapshot', sa.JSON(), nullable=True),
                    sa.Column('note', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('changed_by', sa.String(length=255), nullable=False, server_default=''),
                    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_agent_versions_agent_id', 'agent_versions', ['agent_id'])


def downgrade() -> None:
    op.drop_index('ix_agent_versions_agent_id', table_name='agent_versions')
    op.drop_table('agent_versions')
    op.drop_index('ix_agent_relationships_target_agent_id', table_name='agent_relationships')
    op.drop_index('ix_agent_relationships_source_agent_id', table_name='agent_relationships')
    op.drop_table('agent_relationships')
    op.drop_table('departments')
    op.drop_table('specializations')
    op.drop_index('ix_species_category', table_name='species')
    op.drop_table('species')
    # Plain DROP COLUMN (SQLite >= 3.35 and PostgreSQL): a batch rebuild of `agents` would drop a table that
    # other tables reference, which SQLite refuses while foreign keys are enforced.
    for name in ('ix_agents_lifecycle', 'ix_agents_department_key', 'ix_agents_species_key'):
        op.drop_index(name, table_name='agents')
    for c in reversed(AGENT_COLUMNS):
        op.drop_column('agents', c.name)
