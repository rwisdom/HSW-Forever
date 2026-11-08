# Healer Stat Weights (Forever)

Live healer stat weights for **World of Warcraft Forever**, computed from your own combat log.
Shows the relative value of +Healing (always 1.00), Crit Rating, Haste, Intellect, Spirit and MP5
for the current fight, the last few fights, and a running total, and exports a Pawn string.

Supported specs: Holy Paladin, Restoration Shaman, Restoration Druid, Holy Priest, Discipline Priest.

## Installation

Download the release zip and extract it into your WoW Forever `Interface/AddOns/` folder. The zip
contains a single `HealerStatWeights` folder, so after extraction the addon lives at
`{WoW_Directory}/Interface/AddOns/HealerStatWeights/` with `HealerStatWeights.toc` directly inside it.
Restart the client or `/reload` and enable the addon on the character screen if it is not already.

In game, `/hsw` opens the options and history window. With "Log Casts and Heals per Segment" on
(off by default: the rows live in the saved variables and a raid night can add megabytes), each
logged segment's page has a "Casts and Heals" box with a CSV of every cast, every attributed heal (no
amount: the client hides them) and one total row per spell (time, spell, target, amount, crit, mana)
the weights were built from; click in it, Ctrl+A, Ctrl+C to copy. `/hsw show`, `/hsw hide`, `/hsw lock`,
`/hsw unlock` control the panel. The window's Clear button saves the Total segment (every fight since
login or the last clear) to history as "Total (N fights)" before resetting. `/hsw regen` prints the Spirit-regen rate in use (Forever: 0.25 mana/s
per Spirit under 50 Spirit, 0.125 from 50, gear MP5 taken out) and `/hsw discover on` logs unknown
healing spell IDs, unattributed heals and the fight's pricing steps to chat.

Diagnostics: `/hsw spec` prints the detected spec, `/hsw stats` the character values in use.
`/hsw start` opens a test segment anywhere and prints every heal it allocates; `/hsw end` closes it
and turns the printing off. `/hsw debug` dumps the current segment's counters.

## How weights are computed

Every effective (non-overheal) heal is decomposed into "how much of this heal did one point of each
stat produce" using the spell's Forever coefficient. Mana stats (Intellect mana pool, Spirit regen
inside and outside the five-second rule, MP5) are valued at the healing-per-mana of your filler spells
over the fight, net of the mana Illumination, Water Shield, Litany of Light and the Earthfury set return. Crit includes
that returned mana and Divine Aegis absorbs.

This is a port of Bastas' retail HealerStatWeights (v1.9.1); spell and talent data come from the
talentsforever.com beta export. Forever is in beta: numbers may lag live tuning.

## How it measures on Forever

The Forever client does not let addons read the combat log, and on the release build every heal
amount an addon can see is a secret value. HealerStatWeights watches your own casts
(`UNIT_SPELLCAST_SENT` / `_SUCCEEDED`) and the heals that land on units (`UNIT_COMBAT`: the unit and
the crit flag) and matches the two: a direct heal to your cast on that target, HoT ticks to the HoT
you put on them, Healing Stream Totem to any heal nothing else explains while it is down. That gives
hit and crit counts per spell. The amounts come from Blizzard's built-in damage meter: when the
fight ends and the client releases the numbers (a second or two after combat), the addon reads your
effective healing per spell for the sessions the meter opened during the fight and prices each spell
once from its total, crit-normalised by the counts.

Consequences:
- Weights appear a moment after the fight ends; during the fight the current segment shows zeros.
- Overheal is not recorded by the client and is not counted, which is what the weights are meant to measure.
- A heal from another healer landing on your target within about a second of your cast can be counted as one of your hits. The total is still yours alone; the stray count only shifts the crit normalisation slightly.
- Power Word: Shield is credited at cast with its expected size; Illumination and Water Shield mana is credited on each crit.
- In combat the client hides +Healing, crit chance and buffs: the last out-of-combat reading is used, Inner Focus and Water Shield are tracked from your own casts, Clearcasting procs are not seen.
