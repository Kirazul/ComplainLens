"""Command line: ``uv run complaintlens <command>``.

serve                 start the API (and the email poller if email is configured)
send "text" [...]     process one message locally and print its trace (no email sent)
check                 verify the LLM key and the mailbox credentials work
inbox-create NAME     create a free mail.tm support inbox (no sign-up) and print its settings
set-password USER     set a console password (creates USER as an administrator if new)
"""

from __future__ import annotations

import argparse
import json
import sys


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("complaintlens.api:app", host=args.host, port=args.port, reload=args.reload)


def cmd_send(args: argparse.Namespace) -> None:
    from complaintlens.llm import default_client
    from complaintlens.rag.knowledge import KnowledgeBase
    from complaintlens.schemas import Channel, InboundMessage
    from complaintlens.service import Processor
    from complaintlens.settings import get_settings

    def show(event: dict) -> None:
        if event["type"] == "stage":
            out = {k: v for k, v in event["output"].items() if k not in ("text", "facts")}
            print(f"\n[{event['name']}] {event['status']} · {event['ms']} ms")
            if event.get("note"):
                print(f"  note: {event['note']}")
            print("  " + json.dumps(out, ensure_ascii=False, default=str)[:900])

    from complaintlens.rag.retrieval import build_retriever

    kb = KnowledgeBase.load(get_settings().help_center_dir)
    processor = Processor(kb, default_client(), publish=show, retriever=build_retriever(kb))
    ticket = processor.process(
        InboundMessage(
            channel=Channel.WEB, sender=args.sender, subject=args.subject, body=args.text
        )
    )
    print(
        f"\n=> {ticket.number}: {ticket.status} · team {ticket.team} · priority {ticket.priority}"
    )
    print(f"   reasons: {(ticket.decision or {}).get('reasons')}")


def cmd_check(args: argparse.Namespace) -> None:
    from complaintlens.settings import get_settings

    s = get_settings()
    ok = True
    if s.llm_enabled:
        try:
            from openai import OpenAI

            models = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key).models.list()
            ids = sorted(m.id for m in models.data)
            found = s.llm_model in ids
            print(
                f"LLM: OK ({len(ids)} models). Configured model '{s.llm_model}' available: {found}"
            )
            if not found:
                ok = False
                print("  available:", ", ".join(ids))
        except Exception as exc:
            ok = False
            print(f"LLM: FAILED ({type(exc).__name__}: {exc})")
    else:
        print("LLM: not configured (set LLM_API_KEY in .env); classical fallback will be used")
    if s.email_enabled and s.email_inbox == "mailtm":
        try:
            from complaintlens.channels import mailtm

            mailtm.check_login(s)
            print(f"Email (mail.tm, receive only): OK ({s.email_address})")
        except Exception as exc:
            ok = False
            print(f"Email (mail.tm): FAILED ({type(exc).__name__}: {exc})")
    elif s.email_enabled:
        try:
            from imap_tools import MailBox

            with MailBox(s.imap_host).login(s.email_address, s.email_password) as mb:
                print(f"Email IMAP: OK ({s.email_address}, folder {mb.folder.get()})")
            import smtplib

            with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20) as smtp:
                smtp.login(s.email_address, s.email_password)
            print("Email SMTP: OK")
        except Exception as exc:
            ok = False
            print(f"Email: FAILED ({type(exc).__name__}: {exc})")
    else:
        print("Email: not configured (set EMAIL_ADDRESS and EMAIL_PASSWORD in .env)")
    sys.exit(0 if ok else 1)


def cmd_inbox_create(args: argparse.Namespace) -> None:
    from complaintlens.channels.mailtm import create_inbox

    address, password = create_inbox(args.name)
    print("Inbox created. Put these in .env (and in the hosting service's variables):")
    print("EMAIL_INBOX=mailtm")
    print(f"EMAIL_ADDRESS={address}")
    print(f"EMAIL_PASSWORD={password}")


def cmd_set_password(args: argparse.Namespace) -> None:
    import getpass

    from sqlmodel import select

    from complaintlens import auth
    from complaintlens.store import User, new_session

    username = args.username.strip().lower()
    password = getpass.getpass(f"New password for {username}: ")
    try:
        auth.check_password(password)
    except Exception:
        sys.exit(f"The password needs at least {auth.MIN_PASSWORD} characters.")
    with new_session() as s:
        user = s.exec(select(User).where(User.username == username)).first()
        if user is None:
            auth.check_new_account(username, password)
            user = User(username=username, name=username.title(), role="admin", password_hash="")
        auth.set_password(s, user, password)
    print(f"Password set for {username}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="complaintlens")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("serve", help="run the API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("send", help="process one message locally and print the trace")
    p.add_argument("text")
    p.add_argument("--sender", default="demo.customer@example.com")
    p.add_argument("--subject", default=None)
    p.set_defaults(func=cmd_send)
    p = sub.add_parser("check", help="verify LLM and email credentials")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("inbox-create", help="create a free mail.tm support inbox")
    p.add_argument("name", help="the part before @, e.g. lunagocare")
    p.set_defaults(func=cmd_inbox_create)
    p = sub.add_parser("set-password", help="set a console password (account recovery)")
    p.add_argument("username")
    p.set_defaults(func=cmd_set_password)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
