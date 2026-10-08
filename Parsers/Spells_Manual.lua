local name, addon = ...;
local S, T = addon.Spells, addon.SpellType;

-- Applies fn(entry, id) to every rank of the named spell.
local function eachRank(spellName, fn)
	for id, s in pairs(S) do
		if type(id) == "number" and s.name == spellName then fn(s, id) end
	end
end

--[[----------------------------------------------------------------------------
	Coefficients the JSON tooltips do not carry.
	VERIFY in game (Task 17): /hsw debug should show _SP close to the coefficient.
------------------------------------------------------------------------------]]
eachRank("Tranquility", function(s) s.coeffTick = 0.214 end);       -- Classic value
eachRank("Power Word: Shield", function(s) s.coeff = 0.10 end);     -- Classic value; credited at cast (StatParser:DecompShieldCast)
-- Swiftmend heals "the full duration" of the HoT; approximated as Rejuvenation R11 (4 ticks: coeff 4*0.20, base 776).
S[18562].coeff = 0.80;
S[18562].base = 776;
-- Healing Stream Totem ticks and Prayer of Mending keep coeff 0 (_SP = 0) until measured in game.

--[[----------------------------------------------------------------------------
	Combat-log ids that differ from the spellbook id.
	Pre-filled from Classic; confirm and extend with "/hsw discover on" (Task 17).
	Still unknown: Holy Shock R1 (book 1311606), Penance bolts, Prayer of Mending heal,
	Wild Growth tick, Light's Vigil party heal, Tranquility tick, Healing Stream Totem tick.
------------------------------------------------------------------------------]]
S:Alias(25914, 20473); -- Holy Shock heal, Rank 2
S:Alias(25913, 20929); -- Holy Shock heal, Rank 3
S:Alias(25903, 20930); -- Holy Shock heal, Rank 4

--[[----------------------------------------------------------------------------
	Spec constants, lookup sets, tracked buffs
------------------------------------------------------------------------------]]
addon.Paladin = { DivineFavor = 20216, Illumination = 20272 };
addon.Priest  = { InnerFocus = 14751, InnerFocusDuration = 60, WeakenedSoul = 6788, WeakenedSoulDuration = 15 };
addon.Druid   = { Clearcasting = 16870, Innervate = 29166 };
addon.Shaman  = { WaterShield = 408510, WaterShieldDuration = 600 }; -- VERIFY the cast id in game: /hsw start, cast it, read "Spellcast Discovered"

-- Casts made under these buffs cost no mana: they do not start the five-second rule.
addon.FreeCastBuffs = { [addon.Priest.InnerFocus] = true, [addon.Druid.Clearcasting] = true };

-- Spell ids credited as healing when cast (all Power Word: Shield ranks); never opens a heal expectation.
addon.AbsorbSpells = {};
eachRank("Power Word: Shield", function(_, id) addon.AbsorbSpells[id] = true end);

addon.BuffTracker:Track(addon.Priest.InnerFocus);
addon.BuffTracker:Track(addon.Druid.Clearcasting);
addon.BuffTracker:Track(addon.Shaman.WaterShield);
