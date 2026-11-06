"""Register one agent: python -m jaisa.register Tape|Lekhak|Pothi

Asks for the registration key without echoing it. Tape and Lekhak take
Aryan's key; Pothi takes Mom's, typed by Mom, so Switch records her as its
owner. The agent's own API key lands in keys/<name>.json (mode 600).
"""

import getpass
import sys

from .switch import register

DESCRIPTIONS = {
    "Tape": "Aryan's. Transcribes Mom's recipe voice notes (Marathi) and passes two fixed lines to Pothi.",
    "Lekhak": "Aryan's. Drafts the recipe as word citations into Tape's transcript. Never types a quantity.",
    "Pothi": "Mom's. Checks every quantity against the tape, asks Mom for the gaps, writes the page once.",
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in DESCRIPTIONS:
        raise SystemExit("usage: python -m jaisa.register Tape|Lekhak|Pothi")
    key = getpass.getpass(f"Registration key for {name} (not shown): ").strip()
    if not key:
        raise SystemExit("no key given")
    agent = register(name, DESCRIPTIONS[name], key)
    print(f"{name} registered: {agent['id']} (key saved in keys/{name}.json)")


if __name__ == "__main__":
    main()
