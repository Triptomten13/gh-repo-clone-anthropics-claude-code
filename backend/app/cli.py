"""Operator command line for the machine owner (whoever has shell access to the server).

    python -m app.cli list-users
    python -m app.cli create-admin --email you@example.com          # prompts for a password
    python -m app.cli reset-password --email you@example.com        # prompts; signs out existing sessions
    python -m app.cli set-role --email someone@example.com --role viewer
    python -m app.cli disable --email someone@example.com   |   enable --email ...

Passwords are read interactively (or from stdin with --password-stdin), never from argv,
so they do not end up in shell history or the process list. Every change is audited with
actor "cli:<os user>". Uses DATABASE_URL like the server does.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import func, select

from .db import SessionLocal, init_db
from .governance import core as gov
from .models import User
from .security.auth import hash_password

MIN_PASSWORD = 10


def _actor() -> str:
    try:
        return f"cli:{getpass.getuser()}"
    except Exception:  # pragma: no cover - no passwd entry
        return "cli:unknown"


def _read_password(args: argparse.Namespace) -> str:
    if args.password_stdin:
        pw = sys.stdin.readline().rstrip("\n")
    else:
        pw = getpass.getpass("New password: ")
        if getpass.getpass("Repeat password: ") != pw:
            raise SystemExit("passwords do not match")
    if len(pw) < MIN_PASSWORD:
        raise SystemExit(f"password must be at least {MIN_PASSWORD} characters")
    return pw


def _get(db, email: str) -> User:
    u = db.scalars(select(User).where(User.email == email.lower())).first()
    if not u:
        raise SystemExit(f"no user {email!r}")
    return u


def _active_admins(db) -> int:
    return int(db.scalar(select(func.count(User.id)).where(User.role == "admin", User.disabled.is_(False))) or 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-users")
    for name in ("create-admin", "reset-password"):
        p = sub.add_parser(name)
        p.add_argument("--email", required=True)
        p.add_argument("--password-stdin", action="store_true", help="read the password from the first line of stdin")
    p = sub.add_parser("set-role")
    p.add_argument("--email", required=True)
    p.add_argument("--role", required=True, choices=["admin", "operator", "viewer"])
    for name in ("disable", "enable"):
        sub.add_parser(name).add_argument("--email", required=True)
    args = ap.parse_args(argv)

    if os.getenv("CLI_INIT_DB", "1") == "1":
        init_db()  # create tables on a brand-new SQLite dev database; a no-op when they exist
    db = SessionLocal()
    actor = _actor()
    try:
        if args.cmd == "list-users":
            rows = db.scalars(select(User).order_by(User.id)).all()
            if not rows:
                print("no users yet — run create-admin, or open the web app and create the first account")
            for u in rows:
                print(f"{u.id:>4}  {u.email:<40} {u.role:<9} {'DISABLED' if u.disabled else 'active'}")
            return 0
        if args.cmd == "create-admin":
            existing = db.scalars(select(User).where(User.email == args.email.lower())).first()
            if existing:
                raise SystemExit(f"{args.email} already exists (role {existing.role}); use set-role / reset-password instead")
            u = User(email=args.email.lower(), password_hash=hash_password(_read_password(args)), role="admin")
            db.add(u)
            db.flush()
            gov.audit(db, actor, "user.create", f"user:{u.id}", role="admin", via="cli")
            db.commit()
            print(f"admin {u.email} created — sign in at the web app's /login")
            return 0
        u = _get(db, args.email)
        if args.cmd == "reset-password":
            u.password_hash = hash_password(_read_password(args))
            u.token_version = (u.token_version or 0) + 1
            u.disabled = False
            gov.audit(db, actor, "user.password_reset", f"user:{u.id}", via="cli")
            db.commit()
            print(f"password for {u.email} reset; existing sessions were signed out. "
                  "If the account was locked by failed logins, the lock clears after LOGIN_WINDOW_S or a server restart.")
            return 0
        if args.cmd == "set-role":
            if u.role == "admin" and args.role != "admin" and not u.disabled and _active_admins(db) <= 1:
                raise SystemExit("refused: at least one active admin must remain")
            u.role = args.role
        elif args.cmd == "disable":
            if u.role == "admin" and not u.disabled and _active_admins(db) <= 1:
                raise SystemExit("refused: at least one active admin must remain")
            u.disabled = True
        elif args.cmd == "enable":
            u.disabled = False
        u.token_version = (u.token_version or 0) + 1
        gov.audit(db, actor, f"user.{args.cmd.replace('-', '_')}", f"user:{u.id}", role=u.role, disabled=u.disabled, via="cli")
        db.commit()
        print(f"{u.email}: role={u.role} {'DISABLED' if u.disabled else 'active'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
