#!/usr/bin/env python3
"""Split MeshWithDelays into what it physically is, for the floorplan editor.

  pipeline   ex_controller/mesh/mesh/* : registers between neighbouring tiles. They live in the
             channels inside the array, so they are merged into the tile array; each one is given
             the position of the tile pins it drives or receives (array-relative).
  (each edge group is split into SEGS segments along the edge: mwd_left_0 .. mwd_left_3, and so on)
  mwd_left   skew registers and logic feeding the array's left edge (activations, column 0)
  mwd_top    skew registers and logic feeding the top edge (weights and partial sums, row 0)
  mwd_bottom de-skew registers and logic on the bottom edge (output rows, row 7)
  mwd_in     operand input buffers (a_buf, b_buf, d_buf) and the logic around them
  mwd_ctl    MeshWithDelays control (tag queue, row counters) that reaches no edge

Edge cells are found from connectivity: a MeshWithDelays cell that shares a net with a tile pin or
pipeline register on an edge is seeded with that edge; the rest take the label of their nearest
seeded neighbour (breadth-first through MeshWithDelays cells), weighted by the number of seeds.
Output: fpedit/mwd_split.json = {"group": {inst: label}, "pipe_pos": {inst: [x, y]}}
"""
import collections, json, re

HERE = "/home/sam/Geetus2.0/chipbase-ref/fpedit"
EDGE = 30.0   # um from the array outline that counts as "on the edge"

g = json.load(open(f"{HERE}/flat_graph.json"))
arr = next(n for n in g["nodes"] if n["id"] == "tile_array")
grid = {name: (gx, gy) for gx, gy, name in arr["grid"]}
AW, AH = arr["w"], arr["h"]


def lef_pins(path):
    t = open(path).read(); pins = {}
    for m in re.finditer(r"\n  PIN (\S+)(.*?)\n  END ", t, re.S):
        r = re.search(r"RECT\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", m.group(2))
        if r: pins[m.group(1)] = ((float(r.group(1)) + float(r.group(3))) / 2, (float(r.group(2)) + float(r.group(4))) / 2)
    return pins


tile_pins = lef_pins("/home/sam/Geetus2.0/chipbase-ref/flow/results/asap7/gemmini_ExecuteController_Tile/base/Tile.lef")
nets = []
for ln in open(f"{HERE}/nets_v3flat.tsv"):
    f = ln.rstrip("\n").split("\t")
    if f[0] in ("clock", "reset"): continue
    nets.append([p.split("|") for p in f[1:]])

MWD = "ex_controller/mesh/"; PIPE = "ex_controller/mesh/mesh/"
is_pipe = lambda i: i.startswith(PIPE) and "|Tile|" not in i
# 1) pipeline register positions from the tile pins on their nets
acc = collections.defaultdict(lambda: [0.0, 0.0, 0])
for pins in nets:
    tp = [(grid[i][0] + tile_pins[m][0], grid[i][1] + tile_pins[m][1]) for i, ms, m, d in pins if ms == "Tile" and i in grid and m in tile_pins]
    if not tp: continue
    cx = sum(x for x, _ in tp) / len(tp); cy = sum(y for _, y in tp) / len(tp)
    for i, ms, m, d in pins:
        if i.startswith(PIPE) and ms != "Tile":
            a = acc[i]; a[0] += cx; a[1] += cy; a[2] += 1
pipe_pos = {i: [a[0] / a[2], a[1] / a[2]] for i, a in acc.items()}
# pipeline cells with no tile pin on any net: take the average position of the positioned pipeline
# cells they share nets with, repeated until nothing changes (a register chain ending at an edge)
for _ in range(20):
    add = {}
    for pins in nets:
        pc = [i for i, ms, m, d in pins if i.startswith(PIPE) and ms != "Tile"]
        known = [pipe_pos[i] for i in pc if i in pipe_pos]
        if not known or len(known) == len(pc): continue
        cx = sum(x for x, _ in known) / len(known); cy = sum(y for _, y in known) / len(known)
        for i in pc:
            if i not in pipe_pos and i not in add: add[i] = [cx, cy]
    if not add: break
    pipe_pos.update(add)


SEGS = 4      # each edge is split into this many segments along its length


def edge_of(x, y):
    """Edge-segment label for an array-relative point, or None if it is inside. Segments are numbered
    from the array's bottom-left corner: along y for the left edge, along x for the top and bottom."""
    d = {"mwd_left": x, "mwd_top": AH - y, "mwd_bottom": y}
    k = min(d, key=d.get)
    if d[k] >= EDGE: return None
    t = y / AH if k == "mwd_left" else x / AW
    return f"{k}_{min(max(int(t * SEGS), 0), SEGS - 1)}"


# 2) seed MeshWithDelays cells by the edge points on their nets
mwd_cells = set(); seeds = collections.defaultdict(collections.Counter); adj = collections.defaultdict(set)
for pins in nets:
    here = [i for i, ms, m, d in pins if i.startswith(MWD) and not i.startswith(PIPE)]
    if not here: continue
    mwd_cells.update(here)
    for a in here:
        adj[a].update(h for h in here if h != a)
    for i, ms, m, d in pins:
        pt = None
        if ms == "Tile" and i in grid and m in tile_pins:
            pt = (grid[i][0] + tile_pins[m][0], grid[i][1] + tile_pins[m][1])
        elif i in pipe_pos:
            pt = pipe_pos[i]
        if pt:
            e = edge_of(*pt)
            if e:
                for h in here: seeds[h][e] += 1
# 3) the operand input buffers (a_buf, b_buf, d_buf) hold a whole row of operands for every column and
# both edges, so they are their own group (mwd_in), not part of any edge segment
fixed = {c: "mwd_in" for c in mwd_cells if re.match(r"(a_buf|b_buf|d_buf)", c[len(MWD):])}
label = {c: s.most_common(1)[0][0] for c, s in seeds.items() if c not in fixed}
label.update(fixed)
# 4) propagate: each unlabelled cell takes the most common label among its labelled neighbours,
# repeated until nothing changes (nets touching many MeshWithDelays cells are control fanout: skipped)
nbr = collections.defaultdict(collections.Counter)
for pins in nets:
    here = [i for i, ms, m, d in pins if i.startswith(MWD) and not i.startswith(PIPE)]
    if 1 < len(here) <= 32:
        for a in here:
            nbr[a].update(h for h in here if h != a)
while True:
    add = {}
    for c in mwd_cells:
        if c in label: continue
        votes = collections.Counter()
        for n, w in nbr[c].items():
            if n in label: votes[label[n]] += w
        if votes: add[c] = votes.most_common(1)[0][0]
    if not add: break
    label.update(add)
for c in mwd_cells:
    label.setdefault(c, "mwd_ctl")
# named control structures stay control regardless of their neighbours
for c in mwd_cells:
    r = c[len(MWD):]
    if re.match(r"(tagq|total_rows_q|matmul_id|fire_counter|req_|in_prop|a_written|b_written|d_written)", r):
        label[c] = "mwd_ctl"
json.dump({"group": label, "pipe_pos": pipe_pos}, open(f"{HERE}/mwd_split.json", "w"))
cnt = collections.Counter(label.values())
print("MeshWithDelays split:", dict(cnt), f"; pipeline registers {sum(1 for _ in pipe_pos)} positioned")
