import unittest
from harness import load

SCHEMA_FILES = ["Classes/Compat.lua", "Classes/Util.lua", "Classes/BuffTracker.lua", "Parsers/Spells.lua"]
DATA_FILES = SCHEMA_FILES + ["Parsers/Spells_Generated.lua", "Parsers/Spells_Manual.lua"]


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.lua, self.addon = load(SCHEMA_FILES)
        self.S, self.T = self.addon.Spells, self.addon.SpellType

    def define(self, spell_id, opts, spell_type="PALADIN"):
        return self.lua.eval(f"function(S, T) return S:Define({spell_id}, T.{spell_type}, 'x', {opts}) end")(self.S, self.T)

    def test_defaults(self):
        s = self.define(1, "{ coeff = 0.5, base = 10, mana = 35, cast = 2.5 }")
        self.assertEqual((s.spellID, s.spellType, s.name), (1, 65, "x"))
        self.assertEqual((s.coeff, s.base, s.coeffTick, s.baseTick, s.manaCost), (0.5, 10, 0, 0, 35))
        self.assertEqual((s.canCrit, s.hstHPCT, s.cd, s.filler), (True, True, False, True))
        self.assertEqual((s.castTime, s.duration, s.tick, s.targets, s.party), (2.5, 0, 0, 1, False))
        self.assertIsNone(s.manaCostPctBase)

    def test_timing_and_target_fields(self):
        s = self.define(10, "{ coeffTick = 0.2, baseTick = 8, mana = 25, duration = 12, tick = 3 }")
        self.assertEqual((s.castTime, s.duration, s.tick, s.targets, s.party), (0, 12, 3, 1, False))
        s = self.define(11, "{ coeff = 0.714, base = 506, mana = 405, cast = 2.5, targets = 3 }")
        self.assertEqual(s.targets, 3)
        s = self.define(12, "{ baseTick = 90, cast = -1, duration = 10, tick = 2, party = true }")
        self.assertEqual((s.castTime, s.party), (-1, True))

    def test_cast_cd_and_filler_rules(self):
        self.assertFalse(self.define(2, "{ mana = 25 }").hstHPCT)                 # instant: no HPCT value
        self.assertTrue(self.define(3, "{ mana = 25, cast = -1 }").hstHPCT)       # channeled
        s = self.define(4, "{ mana = 375, cast = -1, cd = true }")
        self.assertEqual((s.cd, s.filler), (True, False))                          # raid cooldown is never a filler
        s = self.define(5, "{ canCrit = false }")
        self.assertEqual((s.canCrit, s.filler), (False, False))                    # no mana cost: not a filler
        s = self.define(6, "{ manaPct = 0.2 }")
        self.assertEqual((s.filler, s.manaCostPctBase, s.manaCost), (True, 0.2, 0))

    def test_alias_and_get(self):
        self.define(20473, "{ coeff = 0.429 }")
        self.S.Alias(self.S, 25914, 20473)
        self.assertEqual(self.S.Get(self.S, 25914).spellID, 20473)
        self.assertEqual(self.S.Get(self.S, "20473").spellID, 20473)
        self.assertIsNone(self.S.Get(self.S, 99))
        self.assertIsNone(self.S.Get(self.S, None))

    def test_is_for_spec(self):
        pri = self.define(7, "{}", "PRIEST")
        pal = self.define(8, "{}", "PALADIN")
        shared = self.define(9, "{}", "SHARED")
        f = lambda s, spec: self.S.IsForSpec(self.S, s, spec)
        self.assertEqual((f(pri, 256), f(pri, 257), f(pri, 65)), (True, True, False))
        self.assertEqual((f(pal, 65), f(pal, 105)), (True, False))
        self.assertEqual((f(shared, 105), f(shared, 264)), (True, True))

    def test_discover_ignored(self):
        self.addon.DiscoverIgnoredSpell(self.addon, 424242)
        s = self.S.Get(self.S, 424242)
        self.assertEqual(s.spellType, -1)
        self.assertFalse(self.S.IsForSpec(self.S, s, 65))


class DataTests(unittest.TestCase):
    def setUp(self):
        _, self.addon = load(DATA_FILES)
        self.S = self.addon.Spells

    def get(self, spell_id):
        return self.S.Get(self.S, spell_id)

    def test_generated_spot_values(self):
        hl = self.get(25292)
        self.assertEqual((hl.name, hl.coeff, hl.base, hl.manaCost, hl.hstHPCT, hl.filler, hl.spellType), ("Holy Light", 0.714, 1580, 660, True, True, 65))
        self.assertEqual((hl.castTime, hl.duration, hl.tick, hl.targets, hl.party), (2.5, 0, 0, 1, False))
        rj = self.get(774)
        self.assertEqual((rj.coeffTick, rj.baseTick, rj.hstHPCT, rj.canCrit), (0.2, 8, False, True))
        self.assertEqual((rj.duration, rj.tick), (12, 3))
        self.assertEqual((self.get(10623).coeff, self.get(10623).targets), (0.714, 3))     # Chain Heal bounces
        self.assertEqual((self.get(740).duration, self.get(740).tick, self.get(740).party), (10, 2, True))   # Tranquility
        self.assertEqual((self.get(5394).duration, self.get(5394).tick, self.get(5394).party), (300, 2, True))  # Healing Stream Totem
        self.assertEqual((self.get(402174).duration, self.get(402174).tick), (2, 1))       # Penance bolts
        self.assertEqual((self.get(408120).duration, self.get(408120).tick, self.get(408120).party), (7, 1, True))   # Wild Growth
        self.assertEqual(self.get(2061).spellType, 5)      # Flash Heal is PRIEST (Holy + Disc)

    def test_manual_overrides_and_aliases(self):
        self.assertEqual(self.get(740).coeffTick, 0.214)
        pws = self.get(10901)
        self.assertEqual((pws.coeff, pws.base, pws.canCrit), (0.10, 928, False))
        sm = self.get(18562)
        self.assertEqual((sm.coeff, sm.base), (0.8, 776))
        self.assertEqual(self.get(25914).spellID, 20473)   # Holy Shock R2 heal event -> book id

    def test_lookup_tables_and_tracked_buffs(self):
        absorbs = self.addon.AbsorbSpells
        self.assertEqual(sorted(int(k) for k in absorbs.keys()), [17, 592, 600, 3747, 6065, 6066, 10898, 10899, 10900, 10901])
        self.assertIsNone(self.addon.ManaReturnSpells)      # mana returns are credited analytically on crits
        self.assertTrue(self.addon.FreeCastBuffs[14751] and self.addon.FreeCastBuffs[16870])
        self.assertEqual((self.addon.Priest.WeakenedSoul, self.addon.Paladin.DivineFavor), (6788, 20216))
        for buff in (14751, 16870, 408510):
            self.assertIsNotNone(self.addon.BuffTracker[buff])
