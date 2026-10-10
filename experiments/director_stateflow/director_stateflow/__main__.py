"""Read local JSON and print Markdown; no network/browser/write by default."""

import argparse
import json
from pathlib import Path

from .formatting import summary
from .model import reduce_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("--view", choices=("codex", "director", "both"), default="both")
    parser.add_argument("--poll-record", type=Path, help="optional local runtime record, verified against OS identity")
    args = parser.parse_args()
    try:
        data = json.loads(args.events.read_text(encoding="utf-8-sig"))
        event = reduce_events(data["events"]).current
        record = json.loads(args.poll_record.read_text(encoding="utf-8-sig")) if args.poll_record else None
        for view in (("director", "codex") if args.view == "both" else (args.view,)):
            print(summary(event, view, record, synced=data.get("synced", False), sample=data.get("sample", False)))
    except (KeyError, ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
