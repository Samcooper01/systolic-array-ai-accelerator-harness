#!/usr/bin/env python3
"""Animated GIF of one Gemmini matmul (weight-stationary): system view on the left, the systolic array
on the right (8 x 8 shown; the real array is 16 x 16). Writes gemmini_dataflow.gif and anim_sheet.png."""
import warnings
warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle
from matplotlib.animation import FuncAnimation, PillowWriter
from PIL import Image, ImageSequence

BG = "#0e1116"; N = 8
A_C = "#ff8a65"; B_C = "#80cbc4"; P_C = "#ffd24d"; MEM = "#9ad1ff"
fig = plt.figure(figsize=(14, 7.4), facecolor=BG)
axS = fig.add_axes([0.01, 0.04, 0.44, 0.86]); axA = fig.add_axes([0.50, 0.04, 0.48, 0.86])
for ax in (axS, axA):
    ax.set_facecolor(BG); ax.axis("off")
axS.set_xlim(0, 100); axS.set_ylim(0, 100); axA.set_xlim(-3.2, N + 1.2); axA.set_ylim(-2.8, N + 2.4)
title = fig.text(0.5, 0.955, "", ha="center", color="white", fontsize=15, fontweight="bold")
sub = fig.text(0.5, 0.918, "", ha="center", color="#cfd8dc", fontsize=10.5)


def sbox(x, y, w, h, t, c):
    axS.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.5", fc=c, ec=c, alpha=0.25, lw=1.5))
    axS.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.5", fc="none", ec=c, lw=1.5))
    axS.text(x + w / 2, y + h / 2, t, ha="center", va="center", color="white", fontsize=9.5, fontweight="bold")
    return (x + w / 2, y + h / 2)


Pm = sbox(4, 84, 24, 10, "Memory (host)", "#9aa0a6"); Pd = sbox(38, 84, 24, 10, "Memory reader /\nwriter", "#5fd18a")
Pb = sbox(4, 58, 28, 12, "Scratchpad banks\n4 x 64 KiB", "#5fd18a"); Pa = sbox(4, 22, 28, 12, "Accumulator\n2 x 32 KiB", "#5fd18a")
Ps = sbox(4, 4, 28, 10, "AccumulatorScale", "#5fd18a"); Px = sbox(44, 40, 22, 12, "Operand mux +\nskew registers", "#4c9be8")
Parr = sbox(72, 30, 24, 32, "16 x 16\nsystolic\narray", "#4c9be8")
for (p, q, l) in [(Pm, Pd, "128 b"), (Pd, Pb, "mvin"), (Pb, Px, "512 b"), (Px, Parr, "A 128 b, B/D 640 b"),
                  (Parr, Pa, "C 320 b"), (Pa, Ps, ""), (Ps, Pd, "mvout")]:
    axS.annotate("", xy=q, xytext=p, arrowprops=dict(arrowstyle="-|>", color="#555c66", lw=1.4, shrinkA=18, shrinkB=18))
    if l:
        axS.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + 1.5, l, color="#8a939c", fontsize=8, ha="center")
tok = [axS.add_patch(Circle((0, 0), 1.6, color=MEM, visible=False)) for _ in range(6)]
for r in range(N):
    for c in range(N):
        axA.add_patch(Rectangle((c + 0.06, N - 1 - r + 0.06), 0.88, 0.88, fc="#1f3a5a", ec="#4c9be8", lw=0.8))
axA.text(N / 2, N + 1.9, "B (weights) and D (bias) in: top edge", ha="center", color=B_C, fontsize=10)
axA.text(-1.7, N / 2, "A in\n(left\nedge)", ha="center", va="center", color=A_C, fontsize=10)
axA.text(N / 2, -2.3, "C out: bottom edge, to the accumulator", ha="center", color=P_C, fontsize=10)
for i, (c, t) in enumerate(((B_C, "weight held in a processing element"), (A_C, "activation (A), moves right"), (P_C, "partial sum, moves down"))):
    axA.add_patch(Circle((-2.9, N + 1.2 - i * 0.55), 0.13, color=c))
    axA.text(-2.6, N + 1.2 - i * 0.55, t, color="#cfd8dc", fontsize=8, va="center")
wgt = [[axA.add_patch(Rectangle((c + 0.12, N - 1 - r + 0.12), 0.28, 0.28, fc=B_C, alpha=0.0, ec="none")) for c in range(N)] for r in range(N)]
atok = [[axA.add_patch(Circle((0, 0), 0.15, color=A_C, visible=False, zorder=5)) for _ in range(N)] for r in range(N)]
ptok = [[axA.add_patch(Circle((0, 0), 0.15, color=P_C, visible=False, zorder=4)) for _ in range(N)] for c in range(N)]
cyc = axA.text(N + 0.9, N + 1.9, "", ha="right", color="#dddddd", fontsize=10)
PH = [("1  mvin (move in)", "Step 1: the memory reader copies inputs and weights into the scratchpad banks, 128 bits per beat", 16),
      ("2  preload", "Step 2: weights (B) shift down the columns and stay in the processing elements (weight-stationary)", N + 5),
      ("3  compute", "Step 3: A enters from the left, each row one cycle behind the row above; partial sums, starting from D, move down", 3 * N + 5),
      ("4  accumulate", "Step 4: C leaves the bottom edge and is added into the accumulator (read, add, write back)", 12),
      ("5  mvout (move out)", "Step 5: AccumulatorScale scales and clips to 8-bit integers; the memory writer sends the result out", 16)]
starts = []; s = 0
for p in PH:
    starts.append(s); s += p[2]
TOTAL = s


def path_pos(seq, t):
    n = len(seq) - 1; u = min(max(t, 0), 0.9999) * n; i = int(u); f = u - i
    return (seq[i][0] + (seq[i + 1][0] - seq[i][0]) * f, seq[i][1] + (seq[i + 1][1] - seq[i][1]) * f)


def update(fr):
    ph = max(i for i in range(len(PH)) if starts[i] <= fr); k = fr - starts[ph]; name, desc, L = PH[ph]
    title.set_text(f"Gemmini dataflow, one matmul  -  {name}"); sub.set_text(desc)
    route = {0: [Pm, Pd, Pb], 1: [Pb, Px, Parr], 2: [Pb, Px, Parr], 3: [Parr, Pa], 4: [Pa, Ps, Pd, Pm]}[ph]
    col = {0: MEM, 1: B_C, 2: A_C, 3: P_C, 4: MEM}[ph]
    for j, t in enumerate(tok):
        tt = (k / max(L - 1, 1)) * 1.4 - j * 0.12; t.set_visible(0 <= tt <= 1)
        if 0 <= tt <= 1:
            t.center = path_pos(route, tt); t.set_color(col)
    for r in range(N):
        for c in range(N):
            wgt[r][c].set_alpha(0.0 if ph < 1 else (0.9 if (ph > 1 or k >= N - r) else 0.0))
    for row in atok + ptok:
        for a in row:
            a.set_visible(False)
    cyc.set_text(f"cycle {k}" if ph in (1, 2) else "")
    if ph == 2:
        for r in range(N):
            for e in range(N):
                x = k - (r + e)
                if -1 <= x <= N - 0.01:
                    a = atok[r][e]; a.center = (x + 0.30, N - 1 - r + 0.70); a.set_visible(True)
        for c in range(N):
            for e in range(N):
                y = k - (c + e) - 1
                if -1 <= y <= N:
                    p = ptok[c][e]; p.center = (c + 0.70, N - 1 - y + 0.30); p.set_visible(True)
    if ph == 3:
        for c in range(N):
            for e in range(3):
                y = N + (k / (L - 1)) * 2.5 - e * 0.8
                if y < N + 2.2:
                    p = ptok[c][e]; p.center = (c + 0.70, N - 1 - y + 0.30); p.set_visible(True)
    return []


anim = FuncAnimation(fig, update, frames=TOTAL, interval=160, blit=False)
anim.save("gemmini_dataflow_raw.gif", writer=PillowWriter(fps=6), dpi=60)
for i, fr in enumerate((5, starts[1] + 6, starts[2] + 11, starts[3] + 5)):
    update(fr); fig.savefig(f"anim_frame_{i}.png", dpi=60, facecolor=BG)
im = Image.open("gemmini_dataflow_raw.gif")
frames = [f.convert("RGB").quantize(colors=48) for f in ImageSequence.Iterator(im)]
frames[0].save("gemmini_dataflow.gif", save_all=True, append_images=frames[1:], duration=170, loop=0, optimize=True)
ims = [Image.open(f"anim_frame_{i}.png") for i in range(4)]
w, h = ims[0].size; sheet = Image.new("RGB", (w * 2, h * 2))
for i, x in enumerate(ims):
    sheet.paste(x, ((i % 2) * w, (i // 2) * h))
sheet.save("anim_sheet.png")
print(f"{TOTAL} frames")
