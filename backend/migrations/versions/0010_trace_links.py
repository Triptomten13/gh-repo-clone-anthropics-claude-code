"""Unambiguous trace links: `trace_id` (the observability run) on llm_calls and tool_invocations; tool invocations get
an explicit `task_id` instead of the overloaded `run_id`.

Before this revision `llm_calls.run_id` meant a G-sus run for G-sus calls but an observability run for calls made
through the internal AI gateway, and `tool_invocations.run_id` held a TASK id — so a replay could pick up another
execution's records. Now: llm_calls.run_id = G-sus run (its original meaning), llm_calls.trace_id = observability run,
tool_invocations.task_id = task, tool_invocations.trace_id = observability run.
Backfill: tool_invocations.task_id ← run_id (its only writer passed task ids). llm_calls rows written before this
revision keep run_id as written and get no trace_id (they cannot be told apart reliably).

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('llm_calls') as b:
        b.add_column(sa.Column('trace_id', sa.Integer(), nullable=True))
        b.create_index('ix_llm_calls_trace_id', ['trace_id'])
    with op.batch_alter_table('tool_invocations') as b:
        b.add_column(sa.Column('task_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('trace_id', sa.Integer(), nullable=True))
    op.execute("UPDATE tool_invocations SET task_id = run_id WHERE run_id IS NOT NULL")
    with op.batch_alter_table('tool_invocations') as b:
        b.drop_index('ix_tool_invocations_run_id')
        b.drop_column('run_id')
        b.create_index('ix_tool_invocations_task_id', ['task_id'])
        b.create_index('ix_tool_invocations_trace_id', ['trace_id'])


def downgrade() -> None:
    with op.batch_alter_table('tool_invocations') as b:
        b.add_column(sa.Column('run_id', sa.Integer(), nullable=True))
    op.execute("UPDATE tool_invocations SET run_id = task_id WHERE task_id IS NOT NULL")
    with op.batch_alter_table('tool_invocations') as b:
        b.drop_index('ix_tool_invocations_trace_id')
        b.drop_index('ix_tool_invocations_task_id')
        b.drop_column('trace_id')
        b.drop_column('task_id')
        b.create_index('ix_tool_invocations_run_id', ['run_id'])
    with op.batch_alter_table('llm_calls') as b:
        b.drop_index('ix_llm_calls_trace_id')
        b.drop_column('trace_id')
