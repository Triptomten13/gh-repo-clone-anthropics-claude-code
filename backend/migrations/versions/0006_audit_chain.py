"""DAEMON AUDIT & PROVENANCE: hash-chained, append-only audit_log.

Adds seq / prev_hash / hash, seals every existing record into the chain in id order (with the audit key configured at
migration time — AUDIT_HMAC_KEY, or derived from SECRET_KEY: run the migration with the production key), installs the
append-only triggers and records the chain head.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('audit_log') as b:
        b.add_column(sa.Column('seq', sa.BigInteger(), nullable=True))
        b.add_column(sa.Column('prev_hash', sa.String(length=64), nullable=False, server_default=''))
        b.add_column(sa.Column('hash', sa.String(length=64), nullable=False, server_default=''))
        b.create_unique_constraint('uq_audit_log_seq', ['seq'])
        b.create_index('ix_audit_log_hash', ['hash'])

    from types import SimpleNamespace
    import json

    from app.governance.audit_chain import GENESIS, TRIGGERS_POSTGRES, TRIGGERS_SQLITE, seal_hash

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, actor, action, target, details, created_at FROM audit_log ORDER BY id")).fetchall()
    prev, seq = GENESIS, 0
    for r in rows:
        seq += 1
        details = r.details if isinstance(r.details, dict) else json.loads(r.details or "{}")
        created = r.created_at
        if isinstance(created, str):  # SQLite returns text here (no ORM type processing)
            from datetime import datetime
            created = datetime.fromisoformat(created)
        h = seal_hash(prev, seq, SimpleNamespace(actor=r.actor, action=r.action, target=r.target, details=details, created_at=created))
        conn.execute(sa.text("UPDATE audit_log SET seq = :s, prev_hash = :p, hash = :h WHERE id = :i"), {"s": seq, "p": prev, "h": h, "i": r.id})
        prev = h
    head = json.dumps({"seq": seq, "hash": prev})
    exists = conn.execute(sa.text("SELECT 1 FROM system_state WHERE key = 'audit_head'")).first()
    if exists:
        conn.execute(sa.text("UPDATE system_state SET value = :v WHERE key = 'audit_head'"), {"v": head})
    else:
        conn.execute(sa.text("INSERT INTO system_state (key, value, updated_at) VALUES ('audit_head', :v, CURRENT_TIMESTAMP)"), {"v": head})
    for ddl in (TRIGGERS_POSTGRES if conn.dialect.name == "postgresql" else TRIGGERS_SQLITE):
        op.execute(ddl)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
    else:
        op.execute("DROP TRIGGER IF EXISTS audit_log_append_only_update")
        op.execute("DROP TRIGGER IF EXISTS audit_log_append_only_delete")
    op.execute("DELETE FROM system_state WHERE key IN ('audit_head', 'audit_anchor')")
    with op.batch_alter_table('audit_log') as b:
        b.drop_index('ix_audit_log_hash')
        b.drop_constraint('uq_audit_log_seq', type_='unique')
        b.drop_column('hash')
        b.drop_column('prev_hash')
        b.drop_column('seq')
