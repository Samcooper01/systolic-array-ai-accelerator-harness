#!/usr/bin/env python3
"""Drive a running fpedit_flat.py and read its state.

  fpctl.py state                      visible nodes with positions, selection, die, score inputs
  fpctl.py show ID [ID ...]           make nodes (and their nets) visible
  fpctl.py hide ID [ID ...]
  fpctl.py only ID [ID ...]           show exactly these
  fpctl.py move ID X Y                lower-left corner (macros) or centre (logic clusters), um
  fpctl.py nudge ID DX DY
  fpctl.py orient ID R0|MX|MY|R180
  fpctl.py die W H
  fpctl.py mode pairs|buses
  fpctl.py select ID
  fpctl.py note "TEXT"                message shown in the editor window
  --text "..." on any command also shows a note with it.
IDs are the editor's node ids (see `state --all`). Commands take effect within half a second.
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CMD = os.path.join(HERE, "cmd"); AUTO = os.path.join(HERE, "flat_graph_autosave.json")


def send(cmds):
    os.makedirs(CMD, exist_ok=True)
    tmp = os.path.join(CMD, f".{time.time_ns()}.tmp"); fin = os.path.join(CMD, f"{time.time_ns()}.json")
    json.dump(cmds, open(tmp, "w")); os.rename(tmp, fin)
    for _ in range(40):          # wait for the editor to consume it
        if not os.path.exists(fin):
            return True
        time.sleep(0.1)
    return False


def state(all_nodes=False):
    g = json.load(open(AUTO)); vis = set(g.get("visible", []))
    print(f"die {g['die']['w']:g} x {g['die']['h']:g}   selected: {g.get('selected')}   mode: {g.get('mode')}   min_bits: {g.get('min_bits')}")
    for n in sorted(g["nodes"], key=lambda n: n["id"]):
        if all_nodes or n["id"] in vis:
            print(f"  {'*' if n['id'] in vis else ' '} {n['id']:40s} x {n['x']:8.1f}  y {n['y']:8.1f}  {n.get('orient', 'R0')}")


def main():
    a = sys.argv[1:]; text = None
    if "--text" in a:
        i = a.index("--text"); text = a[i + 1]; a = a[:i] + a[i + 2:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return
    op, args = a[0], a[1:]
    if op == "state":
        state("--all" in args); return
    c = {"op": op}
    if op in ("show", "hide", "only"): c["ids"] = args
    elif op == "move": c.update(id=args[0], x=float(args[1]), y=float(args[2]))
    elif op == "nudge": c.update(id=args[0], dx=float(args[1]), dy=float(args[2]))
    elif op == "orient": c.update(id=args[0], o=args[1])
    elif op == "die": c.update(w=float(args[0]), h=float(args[1]))
    elif op == "mode": c["m"] = args[0]
    elif op == "select": c["id"] = args[0]
    elif op == "min_bits": c["n"] = int(args[0])
    elif op == "note": text = " ".join(args)
    if text: c["text"] = text
    ok = send([c])
    print("applied" if ok else "not consumed: is the editor running?")


if __name__ == "__main__":
    main()
