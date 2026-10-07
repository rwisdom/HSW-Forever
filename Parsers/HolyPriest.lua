local name, addon = ...;

function addon:IsHolyPriest()
	return self:GetSpecId() == addon.SpellType.HPRIEST;
end

addon.SpecInfo = addon.SpecInfo or {};
addon.SpecInfo[addon.SpellType.HPRIEST] = {
	{
		key = "url",
		name = "talentsforever.com",
		desc = "Forever talent calculator; source of the spell and talent data this addon uses.",
		value = "https://talentsforever.com/",
	},
	{
		key = "Holy Priest\nNotes:",
		value = "Spirit is valued both as regen (Meditation share read from the client) and as +Healing through Spiritual Guidance. Inner Focus adds 25% crit to the next direct heal while the buff is up. Prayer of Mending has no coefficient until measured in game.",
	},
};

--[[----------------------------------------------------------------------------
	Shared by Holy and Discipline (Disc parser reuses these).
------------------------------------------------------------------------------]]
addon.Priest = addon.Priest or {};

-- Inner Focus: +25% crit on the next non-periodic spell while the buff is up.
function addon.Priest.CritChance(ev, s, destUnit, C)
	if ev ~= "SPELL_PERIODIC_HEAL" and addon.BuffTracker:Get(addon.Priest.InnerFocus) > 0 then
		C = C + 0.25;
	end
	return C;
end

-- Spiritual Guidance: 5% of Spirit per rank becomes +Healing, so 1 Spirit = 0.05*rank +Healing.
function addon.Priest.Spirit(ev, s, heal, destUnit, _SP, seg)
	return 0.05 * addon:GetTalentRank("Spiritual Guidance") * _SP;
end

addon.StatParser:Create(addon.SpellType.HPRIEST, {
	CritChance = addon.Priest.CritChance,
	Spirit = addon.Priest.Spirit,
});
