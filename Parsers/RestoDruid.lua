local name, addon = ...;

function addon:IsRestoDruid()
	return self:GetSpecId() == addon.SpellType.DRUID;
end

addon.SpecInfo = addon.SpecInfo or {};
addon.SpecInfo[addon.SpellType.DRUID] = {
	{
		key = "url",
		name = "talentsforever.com",
		desc = "Forever talent calculator; source of the spell and talent data this addon uses.",
		value = "https://talentsforever.com/",
	},
	{
		key = "Resto Druid\nNotes:",
		value = "HoT ticks can crit on Forever, so Crit is valued on every Rejuvenation/Regrowth/Wild Growth/Tranquility tick. Swiftmend is approximated as a Rejuvenation R11 heal. Living Spirit and Heart of the Wild are read from your talents; Reflection, Innervate and Clearcasting are read from the client (regen rates, buffs).",
	},
};

--[[----------------------------------------------------------------------------
	Improved Regrowth: +10% crit chance per rank on Regrowth (direct heal and
	HoT ticks; confirm tick crit rate in game, Task 17).
------------------------------------------------------------------------------]]
local function CritChance(ev, s, destUnit, C)
	if s.name == "Regrowth" then
		C = C + 0.10 * addon:GetTalentRank("Improved Regrowth");
	end
	return C;
end

addon.StatParser:Create(addon.SpellType.DRUID, {
	CritChance = CritChance,
});
