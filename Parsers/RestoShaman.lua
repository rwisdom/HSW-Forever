local name, addon = ...;

function addon:IsRestoShaman()
	return self:GetSpecId() == addon.SpellType.SHAMAN;
end

addon.SpecInfo = addon.SpecInfo or {};
addon.SpecInfo[addon.SpellType.SHAMAN] = {
	{
		key = "url",
		name = "talentsforever.com",
		desc = "Forever talent calculator; source of the spell and talent data this addon uses.",
		value = "https://talentsforever.com/",
	},
	{
		key = "Resto Shaman\nNotes:",
		value = "Crit includes the mana Water Shield returns on heal crits (2% of max mana, valued at filler healing-per-mana) while the shield is up. Intellect includes Mental Quickness (+Healing from Int). Riptide's Chain Heal bonus and Healing Way are captured automatically from the heal amounts. Healing Stream Totem ticks have no coefficient until measured.",
	},
};

--[[----------------------------------------------------------------------------
	Tidal Mastery: +1% crit per rank on healing spells.
------------------------------------------------------------------------------]]
local function CritChance(ev, s, destUnit, C)
	return C + 0.01 * addon:GetTalentRank("Tidal Mastery");
end

--[[----------------------------------------------------------------------------
	Water Shield: a heal crit restores 2% of max mana while a globe remains.
	Value per 1% crit = 0.01 * 0.02 * maxMana * HPM.
------------------------------------------------------------------------------]]
local function CriticalStrike(ev, s, heal, destUnit, C, CB, seg)
	if not s.canCrit or addon.BuffTracker:Get(addon.Shaman.WaterShield) == 0 then return 0 end
	return 0.01 * 0.02 * (addon.ply_maxmana or 0) * seg:GetFillerHPM() / addon.CritConv;
end

--[[----------------------------------------------------------------------------
	Mental Quickness: 15% of Intellect per rank becomes +Healing.
------------------------------------------------------------------------------]]
local function Intellect(ev, s, heal, destUnit, _SP, seg)
	return 0.15 * addon:GetTalentRank("Mental Quickness") * _SP;
end

addon.StatParser:Create(addon.SpellType.SHAMAN, {
	CritChance = CritChance,
	CriticalStrike = CriticalStrike,
	Intellect = Intellect,
});
