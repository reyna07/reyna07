#!/usr/bin/env python3
"""Neon sudoku for a GitHub profile README.

Usage:
  python sudoku/game.py new    # start a fresh puzzle
  python sudoku/game.py move   # apply the move in $ISSUE_TITLE by $ISSUE_USER
"""
import datetime
import html
import json
import os
import random
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "sudoku"
STATE = DIR / "state.json"
BOARD = DIR / "board.svg"
README = ROOT / "README.md"
START, END = "<!-- SUDOKU:START -->", "<!-- SUDOKU:END -->"
TARGET_EMPTY = 45          # how many blanks a new puzzle aims for
REPO = os.environ.get("REPO", "YOUR_USERNAME/YOUR_USERNAME")
REPLY_FILE = Path(os.environ.get("REPLY_FILE", "/tmp/sudoku_reply.md"))


# ---------- puzzle generation ----------

def peers_values(g, i):
    r, c = divmod(i, 9)
    br, bc = r // 3 * 3, c // 3 * 3
    vals = set(g[r * 9:(r + 1) * 9])
    vals |= {g[k * 9 + c] for k in range(9)}
    vals |= {g[(br + a) * 9 + bc + b] for a in range(3) for b in range(3)}
    return vals


def count_solutions(g, limit=2):
    best, best_cands = None, None
    for i in range(81):
        if g[i] == 0:
            cands = [d for d in range(1, 10) if d not in peers_values(g, i)]
            if not cands:
                return 0
            if best is None or len(cands) < len(best_cands):
                best, best_cands = i, cands
                if len(cands) == 1:
                    break
    if best is None:
        return 1
    n = 0
    for d in best_cands:
        g[best] = d
        n += count_solutions(g, limit - n)
        g[best] = 0
        if n >= limit:
            break
    return n


def new_puzzle():
    def pattern(r, c):
        return (3 * (r % 3) + r // 3 + c) % 9
    rows = [g * 3 + r for g in random.sample(range(3), 3) for r in random.sample(range(3), 3)]
    cols = [g * 3 + c for g in random.sample(range(3), 3) for c in random.sample(range(3), 3)]
    nums = random.sample(range(1, 10), 9)
    solution = [nums[pattern(r, c)] for r in rows for c in cols]

    puzzle = solution[:]
    order = list(range(81))
    random.shuffle(order)
    empty = 0
    for i in order:
        if empty >= TARGET_EMPTY:
            break
        keep = puzzle[i]
        puzzle[i] = 0
        if count_solutions(puzzle[:]) == 1:
            empty += 1
        else:
            puzzle[i] = keep
    return puzzle, solution


# ---------- state ----------

def load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"puzzle_no": 0, "solved_total": 0, "leaderboard": {},
            "moves": [], "last_winner": None}


def save(s):
    STATE.write_text(json.dumps(s, indent=1))


def start_puzzle(s):
    givens, solution = new_puzzle()
    s.update(puzzle_no=s["puzzle_no"] + 1, givens=givens,
             solution=solution, board=givens[:], last=None)


# ---------- rendering ----------

FONT = '"Avenir Next", "Segoe UI", Ubuntu, "Helvetica Neue", Arial, sans-serif'


def render_svg(s):
    S, GX, GY = 50, 225, 160
    left = s["board"].count(0)
    o = [f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 760" width="900" height="760" role="img" aria-label="Neon sudoku board, {left} cells left">
  <defs>
    <filter id="neon" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="b1"/>
      <feGaussianBlur in="SourceGraphic" stdDeviation="9" result="b2"/>
      <feMerge><feMergeNode in="b2"/><feMergeNode in="b1"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <radialGradient id="bg" cx="50%" cy="45%" r="70%">
      <stop offset="0" stop-color="#22074a"/><stop offset="1" stop-color="#0e0221"/>
    </radialGradient>
  </defs>
  <style>
    .sign {{ font: 800 54px {FONT}; fill: none; stroke: #ff3fd8; stroke-width: 2.4; letter-spacing: 3px; animation: flicker 6s linear infinite; }}
    .given {{ font: 700 28px {FONT}; fill: #ff3fd8; }}
    .placed {{ font: 600 28px {FONT}; fill: #00f0ff; }}
    .lbl {{ font: 500 16px {FONT}; fill: #c7b8ff; fill-opacity: .7; }}
    .status {{ font: 600 22px {FONT}; fill: #e9e2ff; }}
    .small {{ font: 400 17px {FONT}; fill: #c7b8ff; }}
    @keyframes flicker {{ 0%, 17%, 21%, 24%, 61%, 64%, 100% {{ opacity: 1; }} 19%, 23%, 62.5% {{ opacity: .2; }} }}
  </style>
  <rect width="900" height="760" rx="24" fill="url(#bg)"/>
  <text class="sign" x="450" y="88" text-anchor="middle" filter="url(#neon)">neon sudoku</text>''']

    # labels
    for i in range(9):
        o.append(f'  <text class="lbl" x="{GX + i * S + S / 2}" y="{GY - 12}" text-anchor="middle">{i + 1}</text>')
        o.append(f'  <text class="lbl" x="{GX - 18}" y="{GY + i * S + S / 2 + 6}" text-anchor="middle">{i + 1}</text>')

    # last move highlight
    if s.get("last"):
        r, c = s["last"]
        o.append(f'  <rect x="{GX + c * S + 3}" y="{GY + r * S + 3}" width="{S - 6}" height="{S - 6}" rx="6" fill="#00f0ff" opacity=".25">'
                 f'<animate attributeName="opacity" values=".1;.4;.1" dur="2s" repeatCount="indefinite"/></rect>')

    # grid
    o.append('  <g stroke="#00e5ff" stroke-opacity=".38" stroke-width="1">')
    for i in range(1, 9):
        if i % 3:
            o.append(f'    <line x1="{GX + i * S}" y1="{GY}" x2="{GX + i * S}" y2="{GY + 9 * S}"/>')
            o.append(f'    <line x1="{GX}" y1="{GY + i * S}" x2="{GX + 9 * S}" y2="{GY + i * S}"/>')
    o.append('  </g>')
    o.append('  <g stroke="#b026ff" stroke-width="3" fill="none" filter="url(#neon)">')
    for i in (3, 6):
        o.append(f'    <line x1="{GX + i * S}" y1="{GY}" x2="{GX + i * S}" y2="{GY + 9 * S}"/>')
        o.append(f'    <line x1="{GX}" y1="{GY + i * S}" x2="{GX + 9 * S}" y2="{GY + i * S}"/>')
    o.append(f'    <rect x="{GX}" y="{GY}" width="{9 * S}" height="{9 * S}" rx="4"/>')
    o.append('  </g>')

    # digits
    o.append('  <g text-anchor="middle" dominant-baseline="central" filter="url(#soft)">')
    for i, d in enumerate(s["board"]):
        if d:
            r, c = divmod(i, 9)
            cls = "given" if s["givens"][i] else "placed"
            o.append(f'    <text class="{cls}" x="{GX + c * S + S / 2}" y="{GY + r * S + S / 2 + 1}">{d}</text>')
    o.append('  </g>')

    status = f"Puzzle #{s['puzzle_no']}, {left} cells left"
    o.append(f'  <text class="status" x="450" y="668" text-anchor="middle">{status}</text>')
    if s.get("last_winner"):
        o.append(f'  <text class="small" x="450" y="702" text-anchor="middle">Last puzzle finished by @{html.escape(s["last_winner"])}</text>')
    o.append('</svg>')
    BOARD.write_text("\n".join(o))


def issue_link(r, c):
    title = f"sudoku|r{r + 1}c{c + 1}|?"
    body = ("Replace the ? at the end of the title with a digit from 1 to 9, "
            "then click Submit. You don't need to write anything here.")
    q = urllib.parse.urlencode({"title": title, "body": body})
    return f"https://github.com/{REPO}/issues/new?{q}"


def render_readme(s):
    lines = [START, "",
             '<p align="center"><img src="./sudoku/board.svg" alt="Neon sudoku board" width="70%"/></p>', "",
             "**How to play:** click a **?** in the grid below. A new issue opens; replace the ? at the end of "
             "its title with your digit and click Submit. The board updates in about a minute.", "",
             "|   | " + " | ".join(str(i) for i in range(1, 10)) + " |",
             "|:-:|" + ":-:|" * 9]
    for r in range(9):
        cells = []
        for c in range(9):
            d = s["board"][r * 9 + c]
            cells.append(str(d) if d else f"[**?**]({issue_link(r, c)})")
        lines.append(f"| **{r + 1}** | " + " | ".join(cells) + " |")
    lines.append("")

    if s["moves"]:
        lines.append("**Recent moves**")
        lines.append("")
        for m in s["moves"][:5]:
            mark = "✅" if m["ok"] else "❌"
            lines.append(f"- {mark} @{m['user']} tried {m['digit']} at row {m['r']}, column {m['c']}")
        lines.append("")

    if s["leaderboard"]:
        top = sorted(s["leaderboard"].items(), key=lambda kv: -kv[1])[:5]
        lines.append("**Top solvers**")
        lines.append("")
        lines.append("| Player | Correct digits |")
        lines.append("|:--|:-:|")
        for u, n in top:
            lines.append(f"| [@{u}](https://github.com/{u}) | {n} |")
        lines.append("")
    lines.append(f"Puzzles completed so far: **{s['solved_total']}**")
    lines += ["", END]
    block = "\n".join(lines)

    text = README.read_text() if README.exists() else ""
    if START in text and END in text:
        pre, rest = text.split(START, 1)
        _, post = rest.split(END, 1)
        text = pre + block + post
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    README.write_text(text)


# ---------- moves ----------

def reply(msg):
    REPLY_FILE.write_text(msg)


def play(s, title, user):
    owner = REPO.split("/")[0]
    back = f"[Back to the board](https://github.com/{owner})"
    m = re.fullmatch(r"\s*sudoku\|r([1-9])c([1-9])\|([1-9])\s*", title, re.I)
    if not m:
        reply("I couldn't read that move. The title should look like `sudoku|r3c5|7` "
              "(row 3, column 5, digit 7). Make sure you replaced the **?** with a digit.\n\n" + back)
        return False
    r, c, d = (int(x) for x in m.groups())
    i = (r - 1) * 9 + (c - 1)
    if s["board"][i]:
        reply(f"Row {r}, column {c} is already filled. Pick an empty cell!\n\n{back}")
        return False

    ok = s["solution"][i] == d
    s["moves"].insert(0, {"user": user, "r": r, "c": c, "digit": d, "ok": ok,
                          "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")})
    s["moves"] = s["moves"][:20]
    if not ok:
        reply(f"{d} doesn't belong at row {r}, column {c}. Try another digit!\n\n{back}")
        return True

    s["board"][i] = d
    s["last"] = [r - 1, c - 1]
    s["leaderboard"][user] = s["leaderboard"].get(user, 0) + 1
    left = s["board"].count(0)
    if left == 0:
        s["solved_total"] += 1
        s["last_winner"] = user
        n = s["puzzle_no"]
        start_puzzle(s)
        reply(f"🎉 You placed the final digit and finished puzzle #{n}! A fresh puzzle is up now.\n\n{back}")
    else:
        reply(f"✨ Correct! {d} lit up at row {r}, column {c}. {left} cells to go.\n\n{back}")
    return True


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "move"
    s = load()
    if mode == "new" or "board" not in s:
        start_puzzle(s)
    if mode == "move":
        play(s, os.environ.get("ISSUE_TITLE", ""), os.environ.get("ISSUE_USER", "someone"))
    save(s)
    render_svg(s)
    render_readme(s)


if __name__ == "__main__":
    main()
