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


def crit_per_pct(heal_amount, C, CB=0.5):
    """Healing gained from +1% crit on a non-crit heal of `heal_amount` at crit chance C."""
    return heal_amount * CB / (1 + min(C, 1) * CB) / 100
