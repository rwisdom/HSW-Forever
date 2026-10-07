"""Shared setup for the spec-parser tests (Tasks 8-12). Not a test module."""
from harness import load, CORE_FILES


def talents_lua(cls, tabs):
    """tabs: list of (tabName, [(talentName, rank), ...]) -> Lua that fills STUB.class / STUB.talents."""
    lua_tabs = []
    for name, ts in tabs:
        items = ", ".join(f'{{name="{n}", rank={r}, max=5}}' for n, r in ts)
        lua_tabs.append(f'{{name="{name}", talents={{{items}}}}}')
    return f'STUB.class = "{cls}"; STUB.talents = {{{", ".join(lua_tabs)}}}'


def start(cls, tabs, parser_files, extra=""):
    """Loads core + parser files; talent cache, conversions, player stats ready; one live segment; player cached.
    Stub defaults: SP 200, Holy crit 10% / Nature crit 12%, Int 110, Spirit 60, max mana 3000, Human."""
    lua, addon = load(CORE_FILES + parser_files, setup=talents_lua(cls, tabs) + "\n" + extra)
    lua.execute("""
        local a = HSW_TEST_ADDON
        a.Util.RebuildTalentCache(); a:SetupConversionFactors(); a:UpdatePlayerStats()
        a.SegmentManager:Enqueue("fight"); a.UnitManager.units["Player-1"] = "player"
    """)
    return lua, addon, addon.SegmentManager.Get(addon.SegmentManager, 0)


def heal(addon, ev, spell, amount, crit=False, overheal=0, dest="Player-1"):
    addon.StatParser.DecompHealingForCurrentSpec(addon.StatParser, ev, dest, spell, crit, amount, overheal)


def set_auras(lua, *ids):
    """Auras the stub reports on every unit (player buffs and target debuffs alike), and refreshes BuffTracker."""
    items = ", ".join(f"{{id={i}}}" for i in ids)
    lua.execute(f"STUB.auras = {{ {items} }}; HSW_TEST_ADDON.BuffTracker:UpdatePlayerBuffs()")


def crit_per_pct(heal_amount, C, CB=0.5):
    """Healing gained from +1% crit on a non-crit heal of `heal_amount` at crit chance C."""
    return heal_amount * CB / (1 + min(C, 1) * CB) / 100
