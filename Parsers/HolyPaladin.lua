local name, addon = ...;

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
		value = "Crit includes the mana Illumination returns (50% of base cost on Flash of Light, Holy Light, Holy Shock and Light's Vigil crits), valued at your filler healing-per-mana; the returned mana also comes off the filler mana spent. Holy Power raises the crit healing bonus (+10% per rank on the 50%). Boundless Light adds Holy Shock crit on allies without your Oath of Light, which is tracked from your own cast; the Oath's healing increase is read from the heal amounts. Divine Favor's guaranteed crit is ignored (one heal per 2 minutes). Reverence is read from the client's regen rates.",
	},
};

--[[----------------------------------------------------------------------------
	Holy Power (hotfix 2026-10-30): "increases the critical strike healing bonus of your Holy
	spells by 10%" per rank. Read as a multiplier on the bonus, the Classic reading of the
	"critical strike damage bonus" talents: 50% -> 75% at 5/5. Verify in game (checklist C4).
------------------------------------------------------------------------------]]
local function CritBonus(ev, s, destUnit, CB)
	return CB * (1 + 0.10 * addon:GetTalentRank("Holy Power"));
end

--[[----------------------------------------------------------------------------
	Boundless Light: +15% crit per rank on Holy Shock cast on allies not under our Oath of
	Light. The Oath is marked on its target when we cast it (Events.lua).
------------------------------------------------------------------------------]]
local function CritChance(ev, s, destUnit, C)
	if s.name == "Holy Shock" and not addon.BuffTracker:TargetHas(destUnit, addon.Paladin.OathOfLight) then
		C = C + 0.15 * addon:GetTalentRank("Boundless Light");
	end
	return C;
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
	CritBonus = CritBonus,
	CriticalStrike = CriticalStrike,
	ManaReturn = ManaReturn,
});
