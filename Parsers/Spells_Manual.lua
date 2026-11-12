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
addon.Priest  = { InnerFocus = 14751, InnerFocusDuration = 60, WeakenedSoul = 6788, WeakenedSoulDuration = 15 };
addon.Druid   = { Clearcasting = 16870 };
addon.Shaman  = { WaterShield = 408510, WaterShieldDuration = 600, WaterShieldGlobes = 3, WaterShieldReturn = 0.02 }; -- verified in game 2026-10-21: cast id and aura id are both 408510, 3 charges, 600 s
addon.Paladin = { OathOfLight = 1328548, OathOfLightDuration = 300 }; -- talent spell (hotfix 2026-10-30); marked on its target at cast (Events.lua)
-- Flat healing the Oath adds on its target (build 70753 tooltip: "up to" these, Classic's Blessing of
-- Light R3 numbers; the "up to" is the Classic downrank penalty on spell ranks learned under level 20,
-- which a 15-point talent never meets). Subtracted before the +Healing derivative (Parsers/HolyPaladin.lua).
addon.Paladin.OathBonus = { ["Holy Light"] = 400, ["Flash of Light"] = 115, ["Holy Shock"] = 230 };

--[[----------------------------------------------------------------------------
	Earthfury set bonuses (seen in game 2026-10-22, Stockade log). addon.ply_earthfury counts the pieces worn.
	5 pieces: a Healing Wave or Lesser Healing Wave cast has a 25% chance to return 35% of its base cost.
	8 pieces: Healing Wave jumps to up to two more units, each jump 80% weaker, in the frame of the main heal.
------------------------------------------------------------------------------]]
addon.Shaman.Earthfury = {
	pieces = { "Earthfury Belt", "Earthfury Boots", "Earthfury Bracers", "Earthfury Epaulets", "Earthfury Gauntlets", "Earthfury Helmet", "Earthfury Legguards", "Earthfury Vestments" },
	manaPieces = 5, jumpPieces = 8,
};

--[[----------------------------------------------------------------------------
	Litany of Light (Holy priest, row 5): a heal cast returns 5% per rank of its base cost when
	the previous heal was a different spell (another rank of the same spell is the same spell).
	The previous heal is tracked on every cast, in or out of combat.
------------------------------------------------------------------------------]]
local lastHealCast;

-- Mana a cast of s returns on average: taken off the filler cost (Events.lua). Called for every
-- cast of a database spell so Litany of Light sees the previous heal.
function addon:CastManaReturn(s)
	local back = 0;
	local litany = self:GetTalentRank("Litany of Light");
	if litany > 0 and lastHealCast and lastHealCast ~= s.name then
		back = back + 0.05 * litany * s.manaCost;
	end
	lastHealCast = s.name;
	if (self.ply_earthfury or 0) >= self.Shaman.Earthfury.manaPieces and (s.name == "Healing Wave" or s.name == "Lesser Healing Wave") then
		back = back + 0.25 * 0.35 * s.manaCost;
	end
	return back;
end

-- Water Shield (tooltip seen in game 2026-11-13): "When a spell, melee, or ranged attack hits the
-- caster or when one of the caster's spells gets a critical result, 2% of maximum mana is restored
-- to the caster, expending one water globe." A heal crit of ours is credited as it lands
-- (Parsers/RestoShaman.lua). This credits globes that went any other way, counted from the buff's
-- charges once they can be read. In a fight the mana comes off the filler mana like a crit return.
function addon:CreditWaterShield(globes)
	local mana = globes * self.Shaman.WaterShieldReturn * (self.ply_maxmana or 0);
	if mana <= 0 then return end
	if self.inCombat then self.StatParser:IncManaRestore(mana) else self.ManaDeficit:Gain(mana, nil, "water shield") end
end

-- Units a cast of s jumps to after its target (HealMatcher).
function addon:CastJumps(s)
	if (self.ply_earthfury or 0) < self.Shaman.Earthfury.jumpPieces then return 0 end
	return s.name == "Healing Wave" and 2 or 0;
end

-- Casts made under these buffs cost no mana: they do not start the five-second rule.
addon.FreeCastBuffs = { [addon.Priest.InnerFocus] = true, [addon.Druid.Clearcasting] = true };

-- Spell ids credited as healing when cast (all Power Word: Shield ranks); never opens a heal expectation.
addon.AbsorbSpells = {};
eachRank("Power Word: Shield", function(_, id) addon.AbsorbSpells[id] = true end);

addon.BuffTracker:Track(addon.Priest.InnerFocus);
addon.BuffTracker:Track(addon.Druid.Clearcasting);
addon.BuffTracker:Track(addon.Shaman.WaterShield);
