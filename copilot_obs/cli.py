"""copilot-obs — list and inspect local Copilot sessions.

    python -m copilot_obs list [--json] [--workspace STR] [--model STR]
                               [--since YYYY-MM-DD] [--limit N]
    python -m copilot_obs show <sessionId|prefix> [--json]
    python -m copilot_obs export [--out FILE]      # all sessions as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import vscode
from .models import Session

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


# --------------------------------------------------------------------------- #
# Collection + filtering
# --------------------------------------------------------------------------- #
def collect() -> list[Session]:
    sessions = vscode.load_all()
    # Newest activity first.
    sessions.sort(key=lambda s: (s.last_activity or s.created or _EPOCH), reverse=True)
    return sessions


def _apply_filters(sessions: list[Session], args) -> list[Session]:
    out = sessions
    if getattr(args, "workspace", None):
        q = args.workspace.lower()
        out = [s for s in out if s.workspace and q in s.workspace.lower()]
    if getattr(args, "model", None):
        q = args.model.lower()
        out = [s for s in out if any(q in m.lower() for m in s.models)]
    if getattr(args, "since", None):
        since = datetime.fromisoformat(args.since).astimezone()
        out = [s for s in out if s.last_activity and s.last_activity >= since]
    if getattr(args, "empty", False) is False:
        out = [s for s in out if s.num_turns > 0]
    if getattr(args, "limit", None):
        out = out[: args.limit]
    return out


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _short_model(m: str) -> str:
    return m.split("/", 1)[1] if "/" in m else m


def _fmt_when(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "?"


def _fmt_tokens(s: Session) -> str:
    if s.total_tokens == 0:
        return "-"
    mark = "" if s.has_exact_tokens else "~"
    return f"{mark}{s.total_tokens:,}"


def _fmt_secs(ms: int) -> str:
    return f"{ms / 1000:.0f}s" if ms else "-"


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _table(sessions: list[Session]) -> str:
    rows = []
    for s in sessions:
        models = ",".join(_short_model(m) for m in s.models) or "-"
        rows.append(
            [
                _fmt_when(s.last_activity),
                _truncate(s.label, 42),
                str(s.num_turns),
                _truncate(models, 22),
                _fmt_tokens(s),
                _fmt_secs(s.total_elapsed_ms),
                _truncate(s.workspace.rsplit("/", 1)[-1] if s.workspace else "-", 18),
                s.session_id[:8],
            ]
        )
    headers = ["WHEN", "TITLE", "TURNS", "MODEL(S)", "TOKENS", "TIME", "WORKSPACE", "ID"]
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    line = lambda cols: "  ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
    out = [line(headers), line(["-" * w for w in widths])]
    out += [line(r) for r in rows]
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_list(args) -> int:
    sessions = _apply_filters(collect(), args)
    if args.json:
        print(json.dumps([s.to_dict(include_turns=False) for s in sessions], indent=2))
        return 0
    if not sessions:
        print("No Copilot sessions found.", file=sys.stderr)
        return 0
    print(_table(sessions))
    exact = sum(1 for s in sessions if s.has_exact_tokens)
    tok = sum(s.total_tokens for s in sessions)
    print(
        f"\n{len(sessions)} sessions  ·  {sum(s.num_turns for s in sessions)} queries"
        f"  ·  {tok:,} tokens ({exact} sessions with exact counts)"
        f"  ·  '~' = estimated, '-' = not recorded"
    )
    return 0


def _find(sessions: list[Session], ident: str) -> Session | None:
    for s in sessions:
        if s.session_id == ident:
            return s
    matches = [s for s in sessions if s.session_id.startswith(ident)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Ambiguous id '{ident}' matches {len(matches)} sessions.", file=sys.stderr)
    return None


def cmd_show(args) -> int:
    sessions = collect()
    s = _find(sessions, args.session)
    if s is None:
        print(f"No session matching '{args.session}'.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(s.to_dict(include_turns=True), indent=2))
        return 0
    print(f"Title     : {s.label}")
    print(f"Session   : {s.session_id}  [{s.source}/{s.fmt}]")
    print(f"Editor    : {s.editor or '?'}")
    print(f"Workspace : {s.workspace or '?'}")
    print(f"Created   : {_fmt_when(s.created)}    Last: {_fmt_when(s.last_activity)}")
    print(f"Models    : {', '.join(s.models) or '-'}")
    tok = "exact" if s.has_exact_tokens else ("estimated" if s.total_tokens else "n/a")
    print(
        f"Totals    : {s.num_turns} queries · {s.total_tokens:,} tokens ({tok}) · "
        f"{_fmt_secs(s.total_elapsed_ms)}"
    )
    print("\n  #  WHEN              MODEL                 PROMPT_TOK  COMPL_TOK   TIME   PROMPT")
    print("  " + "-" * 96)
    for t in s.turns:
        pt = f"{t.prompt_tokens:,}" if t.prompt_tokens is not None else "-"
        ct = f"{t.completion_tokens:,}" if t.completion_tokens is not None else "-"
        print(
            f"  {t.index:<2} {_fmt_when(t.when):<17} {_truncate(_short_model(t.model or '-'),20):<20}  "
            f"{pt:>10}  {ct:>9}  {_fmt_secs(t.total_elapsed_ms or 0):>5}   "
            f"{_truncate(t.prompt.replace(chr(10),' '), 40)}"
        )
    return 0


def cmd_export(args) -> int:
    data = [s.to_dict(include_turns=True) for s in collect()]
    text = json.dumps(data, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Wrote {len(data)} sessions to {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="copilot-obs", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="list all Copilot sessions")
    pl.add_argument("--json", action="store_true")
    pl.add_argument("--workspace", help="substring match on workspace path")
    pl.add_argument("--model", help="substring match on model id")
    pl.add_argument("--since", help="only sessions active since YYYY-MM-DD")
    pl.add_argument("--limit", type=int)
    pl.add_argument("--empty", action="store_true", help="include 0-query sessions")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("show", help="show one session's per-query detail")
    ps.add_argument("session", help="session id or unique prefix")
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=cmd_show)

    pe = sub.add_parser("export", help="dump all sessions as JSON")
    pe.add_argument("--out", help="write to file instead of stdout")
    pe.set_defaults(func=cmd_export)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
