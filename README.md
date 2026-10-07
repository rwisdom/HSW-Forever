# Healer Stat Weights (Forever)

Live healer stat weights for **World of Warcraft Forever**, computed from your own combat log.
Shows the relative value of +Healing (always 1.00), Crit Rating, Haste, Intellect, Spirit and MP5
for the current fight, the last few fights, and a running total, and exports a Pawn string.

Supported specs: Holy Paladin, Restoration Shaman, Restoration Druid, Holy Priest, Discipline Priest.

## Installation

Copy this folder into `{WoW_Directory}/Interface/AddOns/HealerStatWeights/`.

In game, `/hsw` opens the options and history window. `/hsw show`, `/hsw hide`, `/hsw lock`,
`/hsw unlock` control the panel. `/hsw regen` prints the current Spirit-regen calibration and
`/hsw discover on` logs unknown healing spell IDs to chat.

## How weights are computed

Every effective (non-overheal) heal is decomposed into "how much of this heal did one point of each
stat produce" using the spell's Forever coefficient. Mana stats (Intellect mana pool, Spirit regen
inside and outside the five-second rule, MP5) are valued at the healing-per-mana of your filler spells
over the fight. Crit includes mana returned by Illumination, Water Shield and Divine Aegis absorbs.

This is a port of Bastas' retail HealerStatWeights (v1.9.1); spell and talent data come from the
talentsforever.com beta export. Forever is in beta: numbers may lag live tuning.
