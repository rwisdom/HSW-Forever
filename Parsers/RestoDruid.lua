local name, addon = ...;

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
		value = "HoT ticks can crit on Forever, so Crit is valued on every Rejuvenation/Regrowth/Wild Growth/Tranquility tick. Swiftmend is approximated as a Rejuvenation R11 heal. Living Spirit, Heart of the Wild and Natural Instinct (+Healing from Intellect) are read from your talents; Reflection, Innervate and Clearcasting are read from the client (regen rates, buffs). Bloom heals (Spirit on HoT expiry) are not attributed yet.",
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

--[[----------------------------------------------------------------------------
	Natural Instinct (Feral, row 5): 12% of Intellect at rank 1 and 25% at rank 2 becomes
	spell healing, so 1 Int = that share of +Healing.
------------------------------------------------------------------------------]]
local NATURAL_INSTINCT = { 0.12, 0.25 };

local function Intellect(ev, s, heal, destUnit, _SP, seg)
	return (NATURAL_INSTINCT[addon:GetTalentRank("Natural Instinct")] or 0) * _SP;
end

addon.StatParser:Create(addon.SpellType.DRUID, {
	CritChance = CritChance,
	Intellect = Intellect,
});
