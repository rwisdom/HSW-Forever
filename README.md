# Healer Stat Weights (Forever)

Live healer stat weights for **World of Warcraft Forever**, computed from your own casts and the
client's built-in damage meter. Shows the relative value of +Healing (always 1.00), Crit Rating,
Haste, Intellect, Spirit and MP5 for the current fight, the last few fights and three running totals,
and exports a Pawn string.

Supported specs: Holy Paladin, Restoration Shaman, Restoration Druid, Holy Priest, Discipline Priest.

## Installation

Download the release zip and extract it into your WoW Forever `Interface/AddOns/` folder. The zip
contains a single `HealerStatWeights` folder, so after extraction the addon lives at
`{WoW_Directory}/Interface/AddOns/HealerStatWeights/` with `HealerStatWeights.toc` directly inside it.
Restart the client or `/reload` and enable the addon on the character screen if it is not already.

## Where it runs

The addon tracks fights only in the content ticked on the Options tab: Dungeons, Raids, Battlegrounds,
or "Always Enabled" for everything including the open world. Outside enabled content the panel is
hidden and pulls are not tracked, so an open-world test needs "Always Enabled" or the window's
start/end button. A fight started with that button is priced like any other, but it must contain
combat: the damage meter opens no session for heals cast between pulls or at a dummy.

In a raid only boss encounters reach the history log; trash still feeds the Trash Total.

## The window

The segment dropdown holds Total (every fight since login or the last clear), Boss Total (boss
encounters and window-button segments), Trash Total (other fights inside dungeons and raids;
open-world pulls feed the Total only), the current fight, and the last few fights. Fights are named
after your hostile target. Inside a dungeon the client hides hostile names, so a trash pull is named
after the mob the damage meter recorded for it once the pull is priced; a pull the meter has nothing
for stays "Trash".

The Clear button saves each total with healing to history as "Total (N fights)", "Boss Total
(N fights)" and "Trash Total (N fights)" before resetting. The Pawn button copies a scale named after
the segment shown.

`/hsw` opens the options and history window. With "Log Casts and Heals per Segment" on (off by
default: the rows live in the saved variables and a raid night can add megabytes), each logged
segment's page has a "Casts and Heals" box with a CSV of every cast, every attributed heal (no amount:
the client hides them) and one total row per spell (time, spell, target, amount, crit, mana) the
weights were built from; click in it, Ctrl+A, Ctrl+C to copy.

Commands: `/hsw show`, `/hsw hide`, `/hsw lock`, `/hsw unlock` control the panel. `/hsw spec` prints
the detected spec, `/hsw stats` the character values in use, `/hsw regen` the Spirit-regen rate
(0.25 mana/s per Spirit under 50 Spirit, 0.125 from 50, gear MP5 taken out). `/hsw discover on`
narrates fight boundaries and pricing to chat and reports unknown healing spells, unattributed heals
and fights the meter recorded no healing for. `/hsw start` opens a test segment anywhere and prints
every heal it allocates; `/hsw end` closes it. `/hsw debug` dumps the current segment's counters.

## How weights are computed

Every effective (non-overheal) heal is decomposed into "how much of this heal did one point of each
stat produce" using the spell's Forever coefficient. Mana stats (Intellect mana pool, Spirit regen
inside and outside the five-second rule, MP5) are valued at the healing-per-mana of your filler spells
over the fight, net of the mana Illumination, Water Shield, Litany of Light and the Earthfury set
return. Crit includes that returned mana and Divine Aegis absorbs.

The Intellect mana pool counts for the share of the pool a fight emptied. The client hides current
mana, so the share is estimated: the mana every cast cost (heals, shocks, totems), less the returned
mana, mana potions and runes at their tooltip average, Spirit regen and gear MP5 over the fight,
divided by maximum mana and kept between 0 and 1. A short pull that barely touches the pool gives
Intellect little; a total adds the shares of its fights.

Conversions Forever does not expose through the API: 14 crit rating per 1% crit; Intellect per 1%
spell crit from a per-class table keyed by level (foreverdb.net values at 30 and 60, interpolated
between them) with an override on the Options tab; haste rating per 1% defaults to 1 (weights read as
Haste per 1%) until the conversion is known, also settable there.

This is a port of Bastas' retail HealerStatWeights (v1.9.1). Spell and talent data come from the
talentsforever.com export of the Forever client (build 1.60.1.70755 with the server hotfixes through
4 Nov 2026); numbers can lag live tuning.

## How it measures on Forever

The Forever client does not let addons read the combat log, and every heal amount an addon can see
is a secret value. HealerStatWeights watches your own casts (`UNIT_SPELLCAST_SENT` / `_SUCCEEDED`)
and the heals that land on units (`UNIT_COMBAT`: the unit and the crit flag) and matches the two: a
direct heal to your cast on that target, HoT ticks to the HoT you put on them, Healing Stream Totem to
any heal nothing else explains while it is down. That gives hit and crit counts per spell. The amounts
come from Blizzard's built-in damage meter: when the fight ends and the client releases the numbers
(a second or two after combat), the addon reads your effective healing per spell for the sessions the
meter opened during the fight and prices each spell once from its total, crit-normalised by the counts.

Consequences and known limits:

- Weights appear a moment after the fight ends; during the fight the current segment shows zeros.
- Overheal is not recorded by the client and is not counted, which is what the weights are meant to
  measure. A fight of pure overheal prices to nothing and does not reach history.
- The meter gives per-spell totals only, no per-target split. Rules that depend on the target (Oath
  of Light, Renewed Hope, Boundless Light) use the target the spell hit most often that fight.
- A heal from another healer landing on your target within about a second of your cast can be
  counted as one of your hits. The total is still yours alone; the stray count only shifts the crit
  normalisation slightly.
- Power Word: Shield is credited at cast with its expected size (Classic coefficient); Illumination
  and Water Shield mana is credited on each crit.
- In combat the client hides +Healing, crit chance and buffs: the last out-of-combat reading is used,
  Inner Focus and Water Shield are tracked from your own casts, Clearcasting procs are not seen.
- Not yet measured or attributed: Prayer of Mending and Healing Stream Totem coefficients, the
  Holy Binding self-heal, Bloom heals on HoT expiry, Riptide tick timing, Holy Power's exact reading.
- Rarely the meter opens no session for a fight; the addon then has nothing to price and says so under
  `/hsw discover on`.
- The mana-pool share does not see Mana Tide or buff MP5 (Mana Spring, Blessing of Wisdom): in a
  fight with those, Intellect reads high, by at most one full pool. Mana potions and runes count at
  their tooltip average, not at what they actually restored.
