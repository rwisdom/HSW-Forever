"""Shared setup for the spec-parser tests. Not a test module."""
from harness import load, CORE_FILES


def talents_lua(cls, tabs):
    """tabs: list of (tabName, [(talentName, rank), ...]) -> Lua that fills STUB.class / STUB.talents."""
    lua_tabs = []
    for name, ts in tabs:
        items = ", ".join(f'{{name="{n}", rank={r}, max=5}}' for n, r in ts)
        lua_tabs.append(f'{{name="{name}", talents={{{items}}}}}')
    return f'STUB.class = "{cls}"; STUB.talents = {{{", ".join(lua_tabs)}}}'


TEST_SETUP = """
    local a = HSW_TEST_ADDON
    a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
    a.SegmentManager:Enqueue("fight"); a.UnitManager.units["Player-1"] = "player"
    -- price the live segment from one spell total, then forget the hits so the next heal() stands alone
    function a.TestTotal(spell, amount)
        local seg, ttl = a.SegmentManager:Get(0), a.SegmentManager:Get("Total")
        a.StatParser:ApplyTotals(seg, { [spell] = amount })
        seg.hits = {}; ttl.hits = {}
    end
"""


def start(cls, tabs, parser_files, extra=""):
    """Loads core + parser files; talent cache, conversions, player stats ready; one live segment; player cached.
    Stub defaults: SP 200, Holy crit 10% / Nature crit 12%, Int 110, Spirit 60, max mana 3000, Human."""
    lua, addon = load(CORE_FILES + parser_files, setup=talents_lua(cls, tabs) + "\n" + extra)
    lua.execute(TEST_SETUP)
    return lua, addon, addon.SegmentManager.Get(addon.SegmentManager, 0)


def heal(addon, ev, spell, amount, crit=False, dest="Player-1"):
    """One heal of `amount` on `dest`, as the fight sees it: counted at landing, priced from the session total at the end."""
    addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, ev, dest, spell, crit)
    addon.TestTotal(spell, amount)


def set_auras(lua, *ids):
    """Auras the stub reports on every unit (player buffs and target debuffs alike), and refreshes BuffTracker."""
    items = ", ".join(f"{{id={i}}}" for i in ids)
    lua.execute(f"STUB.auras = {{ {items} }}; HSW_TEST_ADDON.BuffTracker:UpdatePlayerBuffs()")


def count(addon, ev, spell, crit=False, dest="Player-1"):
    """One heal landing, counted and not yet priced: several of these, then addon.TestTotal, make a fight."""
    addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, ev, dest, spell, crit)


def crit_per_pct(heal_amount, CB=0.5):
    """Healing gained from +1% crit on non-crit healing of `heal_amount`: one more crit in a hundred hits."""
    return heal_amount * CB / 100


def crits(C, CB=0.5):
    """Real healing per point of non-crit healing at crit chance C: +Healing and haste scale the crits too."""
    return 1 + min(C, 1) * CB


def sp_per(addon, spell, amount, tick=False, sp=200):
    """Non-crit healing one point of +Healing adds to `amount` of `spell` (its direct part, or a tick)."""
    s = addon.Spells.Get(addon.Spells, spell)
    coeff, base = (s.coeffTick, s.baseTick) if tick else (s.coeff, s.base)
    return coeff * amount / (base + coeff * sp)
