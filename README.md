# Healer Stat Weights (Forever)

Live healer stat weights for **World of Warcraft Forever**, computed from your own combat log.
Shows the relative value of +Healing (always 1.00), Crit Rating, Haste, Intellect, Spirit and MP5
for the current fight, the last few fights, and a running total, and exports a Pawn string.

Supported specs: Holy Paladin, Restoration Shaman, Restoration Druid, Holy Priest, Discipline Priest.

## Installation

Copy this folder into `{WoW_Directory}/Interface/AddOns/HealerStatWeights/`, or unzip a release
(`tools/release.py patch|minor|major|X.Y.Z` bumps `## Version` in the .toc, commits it, tags
`v<version>` and writes `dist/HealerStatWeights-<version>.zip`, which unpacks to that folder, plus
`dist/HealerStatWeights-<version>-notes.md` with the commits since the previous tag).

In game, `/hsw` opens the options and history window. `/hsw show`, `/hsw hide`, `/hsw lock`,
`/hsw unlock` control the panel. `/hsw regen` prints the Spirit-regen rate in use (Forever: 0.25 mana/s
per Spirit under 50 Spirit, 0.125 from 50, gear MP5 taken out) and `/hsw discover on` logs unknown
healing spell IDs to chat.

Diagnostics: `/hsw spec` prints the detected spec, `/hsw stats` the character values in use.
`/hsw start` opens a test segment anywhere and prints every heal it allocates; `/hsw end` closes it
and turns the printing off. `/hsw debug` dumps the current segment's counters.

## How weights are computed

Every effective (non-overheal) heal is decomposed into "how much of this heal did one point of each
stat produce" using the spell's Forever coefficient. Mana stats (Intellect mana pool, Spirit regen
inside and outside the five-second rule, MP5) are valued at the healing-per-mana of your filler spells
over the fight, net of the mana Illumination, Water Shield and the Earthfury set return. Crit includes
that returned mana and Divine Aegis absorbs.

This is a port of Bastas' retail HealerStatWeights (v1.9.1); spell and talent data come from the
talentsforever.com beta export. Forever is in beta: numbers may lag live tuning.

## How it measures on Forever

The Forever client does not let addons read the combat log. HealerStatWeights instead watches your own casts (`UNIT_SPELLCAST_SENT` / `_SUCCEEDED`) and the heals that land on units (`UNIT_COMBAT`) and matches the two: a direct heal is matched to your cast on that target, HoT ticks to the HoT you put on them (at its tick time, up to three times the expected tick), Healing Stream Totem to any heal nothing else explains while it is down.

Consequences:
- Overheal is not visible. Every heal counts in full, so +Healing and Crit read a little high on overhealed targets.
- A heal from another healer landing on your target within about a second of your cast can be counted as yours.
- Power Word: Shield is credited at cast with its expected size; Illumination and Water Shield mana is credited on each crit.
- In combat the client hides +Healing, crit chance and buffs: the last out-of-combat reading is used, Inner Focus and Water Shield are tracked from your own casts, Clearcasting procs are not seen.
