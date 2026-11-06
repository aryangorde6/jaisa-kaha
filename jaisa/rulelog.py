"""Who set each agent's addressing rule, read from Switch's own log.

    make rule-log                      every agent registration and rule change
    make rule-log AGENT=pothi BY=Mom   Pothi's only, and a check that only Mom changed it

Why the log is enough (Switch 0.31.0's source, read inside the running container):
- Every change to an existing agent's rule goes through one handler,
  PUT /gateway/agents/{id}/addressing-policy (gateway/agents.py:684-725). It runs for the
  owner and for an admin alike, and after the change it always logs
  "Updated addressing policy for agent X (N rules) by user Y".
- Re-registering an agent needs the same owner and leaves its rule alone
  (bridges/agent/protocol/agent_core.py:536-556). Template runs only change agents they
  created themselves.
- So, read from the container's start, the log names everyone who set an agent's rule.
  Only someone with the machine's shell or database could change it without a line
  here (the README's "Neither, stated plainly" column).

Switch logs in UTC; this prints IST. Docker keeps the log until the container is
recreated (`make down` does that), so save the output before you do. It prints agent and
user names and times, never message text.
"""

import re
import sys
from datetime import datetime, timedelta

IST = timedelta(hours=5, minutes=30)
LINE = re.compile(
    r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\S*\s.*?(?:"
    r"Updated addressing policy for agent (\S+) \((\d+) rules?\) by user (.+?)"
    r"|(Re-registered|Registered) agent: (\S+) \(\S+\))\s*$"
)
USAGE = "usage: python -m jaisa.rulelog [--started ISO-TIME] [AGENT] [--by NAME] < switch.log"


def ist(utc: str) -> str:
    t = datetime.fromisoformat(utc.replace("Z", "")[:19]) + IST
    return t.strftime("%a %d %b %H:%M:%S")


def events(log: str):
    """(when in IST, agent, what, by user or None), oldest first, as Switch logged them."""
    for raw in log.splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        when, agent, rules, by, reg, reg_agent = m.groups()
        if agent:
            yield ist(when), agent, f"rule set ({rules} rule{'' if rules == '1' else 's'})", by
        else:
            yield ist(when), reg_agent, reg.lower(), None


def run(argv: list[str], log: str, out=print) -> int:
    args = list(argv)
    started = by = agent = None
    for flag in ("--started", "--by"):
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                out(USAGE)
                return 2
            if flag == "--started":
                started = args[i + 1]
            else:
                by = args[i + 1]
            del args[i:i + 2]
    if len(args) > 1 or (by and not args):
        out(USAGE)
        return 2
    if args:
        agent = args[0].lower()

    out(f"Switch's log, kept since the container started {ist(started)} IST" if started
        else "Switch's log")
    rows = [e for e in events(log) if agent is None or e[1].lower() == agent]
    if not rows:
        out(f"  no registration or rule change logged{' for ' + agent if agent else ''}")
        return 1 if by else 0
    for when, name, what, who in rows:
        out(f"  {when}  {name:<8} {what:<22} {'by user ' + who if who else ''}".rstrip())
    if not by:
        return 0

    changes = [r for r in rows if r[3] is not None]
    k = next((i for i, r in enumerate(changes) if r[3] == by), None)
    if k is None:
        out(f"{agent}: {by} has never set its rule here.")
        return 1
    others = [r for r in changes[k:] if r[3] != by]
    out(f"{agent}: rule set by {by} first at {changes[k][0]} IST; "
        f"changes by anyone else since then: {len(others)}.")
    if k:
        out(f"  (before that, set {k} time(s) by someone else)")
    return 1 if others else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], sys.stdin.read()))
