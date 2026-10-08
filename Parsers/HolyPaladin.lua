local name, addon = ...;

function addon:IsHolyPaladin()
	return self:GetSpecId() == addon.SpellType.PALADIN;
end

addon.SpecInfo = addon.SpecInfo or {};
addon.SpecInfo[addon.SpellType.PALADIN] = {
	{
		key = "url",
		name = "talentsforever.com",
		desc = "Forever talent calculator; source of the spell and talent data this addon uses.",
		value = "https://talentsforever.com/",
	},
	{
		key = "Holy Paladin\nNotes:",
		value = "Crit includes the mana Illumination returns (50% of base cost on Flash of Light, Holy Light, Holy Shock and Light's Vigil crits), valued at your filler healing-per-mana. Divine Favor's guaranteed crit is ignored (one heal per 2 minutes). Reverence is read from the client's regen rates.",
	},
};

--[[----------------------------------------------------------------------------
	Holy Power: +3% crit per rank on Holy Shock, +1% per rank on other spells.
------------------------------------------------------------------------------]]
local function CritChance(ev, s, destUnit, C)
	local rank = addon:GetTalentRank("Holy Power");
	if s.name == "Holy Shock" then
		return C + 0.03 * rank;
	end
	return C + 0.01 * rank;
end

--[[----------------------------------------------------------------------------
	Illumination: a crit on these direct heals returns (0.2 * rank) chance x 50% of
	the spell's base mana cost. Value per 1% crit = 0.01 * chance * 0.5 * cost * HPM.
------------------------------------------------------------------------------]]
local illuminationSpells = { ["Flash of Light"] = true, ["Holy Light"] = true, ["Holy Shock"] = true, ["Light's Vigil"] = true };

local function CriticalStrike(ev, s, heal, destUnit, C, CB, seg)
	if ev == "SPELL_PERIODIC_HEAL" or not illuminationSpells[s.name] then return 0 end
	local rank = addon:GetTalentRank("Illumination");
	if rank == 0 then return 0 end
	return 0.01 * (0.2 * rank) * 0.5 * s.manaCost * seg:GetFillerHPM() / addon.CritConv;
end

-- The mana an Illumination proc actually returns on this crit: (0.2 * rank) chance x 50% of the
-- spell's base cost. There is no energize event on Forever, so it is credited here.
local function ManaReturn(ev, s, heal, destUnit)
	if ev == "SPELL_PERIODIC_HEAL" or not illuminationSpells[s.name] then return 0 end
	return 0.2 * addon:GetTalentRank("Illumination") * 0.5 * s.manaCost;
end

addon.StatParser:Create(addon.SpellType.PALADIN, {
	CritChance = CritChance,
	CriticalStrike = CriticalStrike,
	ManaReturn = ManaReturn,
});
