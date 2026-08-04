"""Run one assumption probe and record what actually happened, so a feasibility claim is evidence
rather than an assertion.

WHAT THIS IS NOT: proof that a plan will work. That would mean knowing the outcome of executing it
without executing it. This is the opposite and cheaper thing — FALSIFICATION. It kills a plan that
cannot work, before anyone reads it, by checking the few assumptions whose falsity would sink it.
A passing probe means "this did not fail here", never "this will succeed".

The control that makes a verdict worth anything is that the EXPECTATION is stated before the run.
A probe with no pre-stated expectation is UNPROVEN by definition, however cleanly it exits — because
a command that runs and asserts nothing can be made to pass by writing a command that does nothing.

  run     execute one probe under a timeout and print the record
  verify  read a set of records and say whether the tier's probe budget was actually met

The record carries argv, exit code, duration and a hash of the output, so "the probe ran" is checkable
rather than claimed. The honest limit, stated plainly: this proves A command ran and what it returned.
It cannot prove the command was the RIGHT one — that is why the probe and its expectation are shown
to a person before it runs.

Writes only where the caller points it, never into `~/.hercules`, and refuses rather than guessing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNCONFIRMED = 2
EXIT_INTERNAL = 3
EXIT_NOT_FOUND = 4

PASS = "PASS"
FAIL = "FAIL"
UNPROVEN = "UNPROVEN"

_RULES_FILE = "doc_rules.json"
_OUTPUT_CAP = 2000


class Refused(Exception):
    """A precondition rejected the run. Carries the scripted message the caller relays verbatim."""

    def __init__(self, message: str, detail=None):
        super().__init__(message)
        self.message = message
        self.detail = detail or []


def load_rules(script_dir: Path) -> dict:
    path = script_dir / _RULES_FILE
    if not path.exists():
        raise Refused("the standard is missing at %s — reinstall the plugin" % path)
    return json.loads(path.read_text(encoding="utf-8"))


def budget_for(rules: dict, tier: str) -> dict:
    probes = rules["probes"]
    if tier not in probes["tiers"]:
        raise Refused("unknown tier %r — expected one of %s"
                      % (tier, ", ".join(sorted(probes["tiers"]))))
    return probes["tiers"][tier]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def execute(argv, cwd: str, timeout_seconds: int) -> dict:
    """Run the command and describe what happened. A timeout is not a failure of the plan — it is a
    failure to check cheaply, which is a different and less alarming thing."""
    started = time.time()
    try:
        completed = subprocess.run(list(argv), cwd=cwd or None, capture_output=True,
                                   text=True, timeout=timeout_seconds)
        out, err, code, timed_out = completed.stdout, completed.stderr, completed.returncode, False
    except subprocess.TimeoutExpired:
        out, err, code, timed_out = "", "", None, True
    except FileNotFoundError as missing:
        out, err, code, timed_out = "", str(missing), None, False
    return {
        "argv": list(argv),
        "cwd": cwd or "",
        "exit_code": code,
        "timed_out": timed_out,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout_sha256": _digest(out),
        "stderr_sha256": _digest(err),
        "output_head": (out or err)[:_OUTPUT_CAP],
    }


def judge(record: dict, expectation: str, faked) -> tuple:
    """PASS only when the probe ran, exited zero, and had something to be measured against.

    The mock ban lives here: a probe may fake internal units that do not exist yet, but faking the
    dependency, API or data the probe exists to check makes it green precisely where production
    fails. That is not a pass, it is a costume."""
    if not str(expectation or "").strip():
        return UNPROVEN, "no expectation was stated before the run, so nothing was measured"
    if faked:
        return FAIL, ("the probe faked %s, which is what it was meant to check"
                      % ", ".join(sorted(faked)))
    if record["timed_out"]:
        return UNPROVEN, "the probe ran out of time; the assumption is too costly to check here"
    if record["exit_code"] is None:
        return UNPROVEN, "the command could not be started here"
    if record["exit_code"] != 0:
        return FAIL, "the probe exited %d, contradicting the expectation" % record["exit_code"]
    return PASS, "ran clean against a stated expectation"


def run_probe(rules: dict, args) -> tuple:
    if not args.label:
        raise Refused("a probe needs --label naming the assumption it checks")
    if not args.command:
        raise Refused("a probe needs a command after `--`")
    budget = budget_for(rules, args.tier or "medium")
    if budget["probes"] == 0:
        raise Refused("tier %s runs no probes — nothing to check here" % (args.tier or "medium"))

    faked = [item.strip() for item in (args.faked or "").split(",") if item.strip()]
    banned = [item for item in faked
              if item.lower() in {word.lower() for word in rules["probes"]["never_fake"]}]
    record = execute(args.command, args.cwd, min(int(args.timeout or budget["seconds"]),
                                                 budget["seconds"]))
    verdict, why = judge(record, args.expect, banned)

    payload = {
        "mode": "run",
        "label": args.label,
        "scenario": args.scenario or "",
        "tier": args.tier or "medium",
        "expectation": args.expect or "",
        "faked": faked,
        "verdict": verdict,
        "why": why,
        "record": record,
        "rules_version": rules["rules_version"],
    }
    if args.into:
        destination = Path(args.into)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError as unwritable:
            raise Refused("could not write the probe record to %s: %s"
                          % (destination, unwritable)) from unwritable
    return payload, EXIT_OK if verdict == PASS else EXIT_REFUSED


def run_verify(rules: dict, args) -> tuple:
    """Did this session actually check what its tier asks, and is UNPROVEN being used as an escape
    hatch? Both are arithmetic over the records, so the answer is the same every time."""
    folder = Path(args.into or ".")
    if not folder.is_dir():
        raise Refused("no probe records at %s" % folder)
    records = []
    for path in sorted(folder.glob("probe-*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue

    tier = args.tier or "medium"
    budget = budget_for(rules, tier)
    verdicts = [record.get("verdict") for record in records]
    counts = {name: verdicts.count(name) for name in (PASS, FAIL, UNPROVEN)}
    reasons = []

    if counts[FAIL]:
        reasons.append("%d probe(s) contradicted the plan" % counts[FAIL])
    if len(records) < budget["probes"]:
        reasons.append("tier %s asks for %d probe(s); %d ran"
                       % (tier, budget["probes"], len(records)))
    unproven_share = (counts[UNPROVEN] / len(records)) if records else 0
    if records and unproven_share > rules["probes"]["unproven_ceiling"]:
        reasons.append("%d of %d probes are UNPROVEN — too much of this plan is unchecked to call it "
                       "examined" % (counts[UNPROVEN], len(records)))

    payload = {
        "mode": "verify",
        "tier": tier,
        "counts": counts,
        "required": budget["probes"],
        "ran": len(records),
        "labels": [record.get("label") for record in records],
        "decision": "proceed" if not reasons else "not-ready",
        "reasons": reasons or ["the tier's probes ran and none contradicted the plan"],
        "rules_version": rules["rules_version"],
    }
    return payload, EXIT_OK if not reasons else EXIT_REFUSED


def run_budget(rules: dict, args) -> tuple:
    return {"mode": "budget", "rules_version": rules["rules_version"],
            "probes": rules["probes"]}, EXIT_OK


def emit(payload: dict, code: int) -> int:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="probe_run",
        description="Falsify an assumption cheaply, and record what happened.")
    parser.add_argument("mode", choices=("run", "verify", "budget"))
    parser.add_argument("--label", dest="label", default="")
    parser.add_argument("--scenario", dest="scenario", default="")
    parser.add_argument("--expect", dest="expect", default="",
                        help="what you expect to observe — stated BEFORE the run, or the verdict "
                             "is UNPROVEN however cleanly it exits")
    parser.add_argument("--faked", dest="faked", default="",
                        help="comma-separated list of what this probe stands in for")
    parser.add_argument("--tier", dest="tier", default="")
    parser.add_argument("--timeout", dest="timeout", default="")
    parser.add_argument("--cwd", dest="cwd", default="")
    parser.add_argument("--into", dest="into", default="")
    parser.add_argument("command", nargs="*", default=[])
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1:]
    else:
        command = []
    args = build_parser().parse_args(argv)
    args.command = args.command or command
    try:
        rules = load_rules(Path(__file__).resolve().parent)
        if args.mode == "run":
            payload, code = run_probe(rules, args)
        elif args.mode == "verify":
            payload, code = run_verify(rules, args)
        else:
            payload, code = run_budget(rules, args)
        return emit(payload, code)
    except Refused as refusal:
        missing = refusal.message.startswith("no ")
        return emit({"mode": args.mode, "error": "refused", "message": refusal.message,
                     "detail": refusal.detail},
                    EXIT_NOT_FOUND if missing else EXIT_REFUSED)
    except json.JSONDecodeError as broken:
        return emit({"mode": args.mode, "error": "internal",
                     "message": "not valid JSON: %s" % broken}, EXIT_INTERNAL)
    except OSError as unreadable:
        return emit({"mode": args.mode, "error": "internal",
                     "message": "cannot read: %s" % unreadable}, EXIT_INTERNAL)


if __name__ == "__main__":
    sys.exit(main())
