#!/usr/bin/env python3
"""Generate Parsers/Spells_Generated.lua from the talentsforever.com JSON exports in .claude/docs.

Usage:
    python tools/gen_spells.py          # (re)write Parsers/Spells_Generated.lua
    python tools/gen_spells.py --check  # only list entries whose tooltip could not be fully parsed
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / ".claude" / "docs"
OUT = ROOT / "Parsers" / "Spells_Generated.lua"

# Spells to export per class JSON file, with the Lua SpellType constant for that class.
WHITELIST = {
    "druid": ("DRUID", ["Healing Touch", "Rejuvenation", "Regrowth", "Wild Growth", "Tranquility", "Swiftmend"]),
    "paladin": ("PALADIN", ["Holy Light", "Flash of Light", "Holy Shock", "Light's Vigil", "Lay on Hands"]),
    "priest": ("PRIEST", ["Lesser Heal", "Heal", "Greater Heal", "Flash Heal", "Renew", "Prayer of Healing",
                          "Holy Nova", "Binding Heal", "Prayer of Mending", "Penance", "Power Word: Shield",
                          "Desperate Prayer", "Divine Grace"]),
    "shaman": ("SHAMAN", ["Healing Wave", "Lesser Healing Wave", "Chain Heal", "Riptide", "Healing Stream Totem"]),
}
# Seconds between HoT ticks. Not in the JSON — verify in game (Task 17) and regenerate if wrong.
TICK_INTERVAL = {"Rejuvenation": 3, "Regrowth": 3, "Renew": 3, "Riptide": 3, "Wild Growth": 1,
                 "Tranquility": 2, "Penance": 1, "Healing Stream Totem": 2}
RAID_COOLDOWN = {"Tranquility", "Lay on Hands", "Divine Grace", "Desperate Prayer"}   # excluded by the "raid cooldowns" option
NO_CRIT = {"Power Word: Shield", "Lay on Hands"}
# Seconds a periodic effect lasts when its tooltip does not say (totems stay until replaced; 5 min).
HOT_DURATION = {"Healing Stream Totem": 300}
# Direct heals that land on several units at once (Chain Heal bounces, party heals).
MULTI_TARGET = {"Chain Heal": 3, "Prayer of Healing": 5, "Holy Nova": 5}
# Periodic heals that tick on every group member, not only the cast target.
PARTY_HOT = {"Wild Growth", "Tranquility", "Healing Stream Totem"}

NUM = r"(\d[\d,]*)"
RE_CO = re.compile(r"([\d.]+)% of spell power \((heal|per tick|direct)\)")
RE_RANGE = [re.compile(p) for p in (
    NUM + r" to " + NUM + r" healing to an ally",   # Holy Shock (its damage part has no "for")
    r"for " + NUM + r" to " + NUM,                  # most direct heals, Holy Nova, Light's Vigil party heal
)]
RE_SINGLE = [re.compile(p) for p in (
    NUM + r" healing to an ally",                   # Penance
    r"absorbing " + NUM + r" damage",               # Power Word: Shield
    r"for " + NUM + r" the next time",              # Prayer of Mending
)]
RE_HOT = re.compile(r"(?:for|another|additional|of) " + NUM + r"(?: damage)? over (\d+) sec")   # "N over D sec"
RE_EVERY = re.compile(r"for " + NUM + r" every (\d+) sec")                                      # "N every D sec(onds)"
RE_EVERY_FOR = re.compile(r"every (\d+) sec(?:onds)? for (\d+) sec")                            # "every I sec for D sec"
RE_EVERY_ONLY = re.compile(r"every (\d+) sec")                                                   # "every I sec(onds)" with no duration
RE_MANA = re.compile(r"^([\d,]+) Mana$")
RE_MANA_PCT = re.compile(r"^(\d+)% of base mana$")
RE_CAST = re.compile(r"^([\d.]+) sec cast$")


def num(s):
    return int(s.replace(",", ""))


def parse_co(co):
    """'28.6% of spell power (heal), 7.1% of spell power (per tick)' -> (coeff, coeffTick). '(direct)' is damage: ignored."""
    coeff = tick = None
    for pct, kind in RE_CO.findall(co or ""):
        if kind == "heal":
            coeff = round(float(pct) / 100, 4)
        elif kind == "per tick":
            tick = round(float(pct) / 100, 4)
    return coeff, tick


def parse_desc(name, d):
    """Tooltip text -> (base, baseTick); either is None when the text has no such number."""
    base = tick = None
    for rx in RE_RANGE:
        m = rx.search(d)
        if m:
            base = (num(m.group(1)) + num(m.group(2))) / 2
            break
    if base is None:
        for rx in RE_SINGLE:
            m = rx.search(d)
            if m:
                base = num(m.group(1))
                break
    m = RE_HOT.search(d)
    if m:
        total, duration = num(m.group(1)), int(m.group(2))
        interval = TICK_INTERVAL.get(name)
        if interval:
            tick = round(total / (duration / interval), 2)
    else:
        m = RE_EVERY.search(d)
        if m:
            tick = num(m.group(1))
    return base, tick


def parse_hot(name, d):
    """Periodic timing -> (duration, interval) in seconds; (None, None) when the text has no periodic part
    or the interval for this spell is unknown."""
    m = RE_HOT.search(d)
    if m:
        interval = TICK_INTERVAL.get(name)
        return (int(m.group(2)), interval) if interval else (None, None)
    m = RE_EVERY_FOR.search(d)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = RE_EVERY_ONLY.search(d)
    if m:
        duration = HOT_DURATION.get(name)
        return (duration, int(m.group(1))) if duration else (None, None)
    return None, None


def parse_l(l):
    """Flattens the tooltip cell rows. Returns {mana, manaPct, cast} (cast -1 = channeled; absent = instant)."""
    out = {}
    for cell in (c for row in (l or []) for c in row):
        m = RE_MANA.match(cell)
        if m:
            out["mana"] = num(m.group(1))
            continue
        m = RE_MANA_PCT.match(cell)
        if m:
            out["manaPct"] = int(m.group(1)) / 100
            continue
        m = RE_CAST.match(cell)
        if m:
            out["cast"] = float(m.group(1))
            continue
        if cell == "Channeled":
            out["cast"] = -1
    return out


def build_entry(spell_type, name, rank, entry):
    coeff, coeff_tick = parse_co(entry.get("co"))
    base, base_tick = parse_desc(name, entry.get("d") or "")
    if coeff_tick is not None and base_tick is None and base is not None:
        base_tick = base  # Penance: every bolt heals the same amount
    opts = parse_l(entry.get("l"))
    if coeff is not None:
        opts["coeff"] = coeff
    if base is not None:
        opts["base"] = base
    if coeff_tick is not None:
        opts["coeffTick"] = coeff_tick
    if base_tick is not None:
        opts["baseTick"] = base_tick
    if name in RAID_COOLDOWN:
        opts["cd"] = True
    if name in NO_CRIT:
        opts["canCrit"] = False
    duration, interval = parse_hot(name, entry.get("d") or "")
    if duration and interval:
        opts["duration"] = duration
        opts["tick"] = interval
    if name in MULTI_TARGET:
        opts["targets"] = MULTI_TARGET[name]
    if name in PARTY_HOT:
        opts["party"] = True
    notes = []
    if not entry.get("co"):
        notes.append("no coefficient in JSON")
    if base is None and base_tick is None:
        notes.append("tooltip not parsed")
    return {"id": entry["id"], "type": spell_type, "name": name, "rank": rank, "opts": opts, "notes": notes}


KEY_ORDER = ["coeff", "base", "coeffTick", "baseTick", "mana", "manaPct", "cast", "cd", "canCrit", "duration", "tick", "targets", "party"]


def lua_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v)


def render_entry(e):
    opts = ", ".join(f"{k} = {lua_value(e['opts'][k])}" for k in KEY_ORDER if k in e["opts"])
    bits = [e["rank"]] if e["rank"] else []
    if e["notes"]:
        bits.append("(" + "; ".join(e["notes"]) + ")")
    comment = (" -- " + " ".join(bits)) if bits else ""
    lname = e["name"].replace('"', '\\"')
    return f'S:Define({e["id"]}, T.{e["type"]}, "{lname}", {{ {opts} }});{comment}'


def rank_number(rank):
    m = re.search(r"\d+", rank)
    return int(m.group()) if m else 0


def collect():
    """All whitelisted entries from the four JSON files, ordered by whitelist position then rank."""
    entries = []
    for cls, (spell_type, names) in WHITELIST.items():
        data = json.loads((DOCS / f"{cls}.json").read_text(encoding="utf-8"))
        order = {n: i for i, n in enumerate(names)}
        found = []
        for key, entry in data["spell_desc"].items():
            _, name, rank = key.split("|", 2)
            if name in order:
                found.append((order[name], rank_number(rank), build_entry(spell_type, name, rank, entry)))
        missing = set(names) - {e["name"] for _, _, e in found}
        if missing:
            print(f"warning: {cls}.json has no spell_desc for {sorted(missing)}", file=sys.stderr)
        found.sort(key=lambda x: (x[0], x[1]))
        entries.extend(e for _, _, e in found)
    return entries


HEADER = """-- GENERATED by tools/gen_spells.py from .claude/docs/{druid,paladin,priest,shaman}.json - do not edit by hand.
-- Overrides, combat-log aliases and spells the tooltips do not describe live in Parsers/Spells_Manual.lua.
local name, addon = ...;
local S, T = addon.Spells, addon.SpellType;
"""


def render(entries):
    lines = [HEADER]
    current = None
    for e in entries:
        if e["name"] != current:
            current = e["name"]
            lines.append(f"\n-- {current}\n")
        lines.append(render_entry(e) + "\n")
    return "".join(lines)


def main(argv):
    entries = collect()
    if "--check" in argv:
        for e in entries:
            if e["notes"]:
                print(f'{e["id"]:>8}  {e["name"]} {e["rank"]}: {"; ".join(e["notes"])}')
        return 0
    OUT.write_text(render(entries), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(entries)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
