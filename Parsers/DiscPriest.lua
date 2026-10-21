local name, addon = ...;

function addon:IsDiscPriest()
	return self:GetSpecId() == addon.SpellType.DPRIEST;
end

addon.SpecInfo = addon.SpecInfo or {};
addon.SpecInfo[addon.SpellType.DPRIEST] = {
	{
		key = "url",
		name = "talentsforever.com",
		desc = "Forever talent calculator; source of the spell and talent data this addon uses.",
		value = "https://talentsforever.com/",
	},
	{
		key = "Discipline Priest\nNotes:",
		value = "Power Word: Shield absorbs count as healing (coefficient is an estimate until measured). Crit includes Divine Aegis absorbs (direct heals only, capped at 1,200) and Renewed Hope on Weakened Soul targets. Penance bolts are treated as direct heals for both. Mental Strength and Meditation are read from talents/client.",
	},
};

--[[----------------------------------------------------------------------------
	Renewed Hope: +2% crit per rank on these heals when the target has Weakened Soul.
	Penance is listed by the talent, so its bolts count even when logged as periodic.
------------------------------------------------------------------------------]]
local renewedHopeSpells = { ["Flash Heal"] = true, ["Binding Heal"] = true, ["Lesser Heal"] = true, ["Heal"] = true, ["Greater Heal"] = true, ["Penance"] = true };

local function CritChance(ev, s, destUnit, C)
	C = addon.Priest.CritChance(ev, s, destUnit, C);
	if renewedHopeSpells[s.name] and (ev ~= "SPELL_PERIODIC_HEAL" or s.name == "Penance") then
		local rank = addon:GetTalentRank("Renewed Hope");
		local weakened = addon.BuffTracker:TargetHas(destUnit, addon.Priest.WeakenedSoul);
		if HSW_ENABLE_FOR_TESTING and weakened then addon:Msg("Weakened Soul on " .. tostring(destUnit) .. ", Renewed Hope rank " .. rank) end
		if rank > 0 and weakened then
			C = C + 0.02 * rank;
		end
	end
	return C;
end

--[[----------------------------------------------------------------------------
	Divine Aegis: a non-periodic crit heal also absorbs 5% per rank of the crit amount, up to 1,200.
	Value per 1% crit = 0.01 * min(0.05 * rank * heal * (1 + CB), 1200). HoT ticks do not proc it;
	Penance bolts count as direct heals (same as Renewed Hope).
------------------------------------------------------------------------------]]
local DIVINE_AEGIS_CAP = 1200;

local function CriticalStrike(ev, s, heal, destUnit, C, CB, seg)
	if not s.canCrit or (ev == "SPELL_PERIODIC_HEAL" and s.name ~= "Penance") then return 0 end
	local rank = addon:GetTalentRank("Divine Aegis");
	if rank == 0 then return 0 end
	return 0.01 * math.min(0.05 * rank * heal * (1 + CB), DIVINE_AEGIS_CAP) / addon.CritConv;
end

addon.StatParser:Create(addon.SpellType.DPRIEST, {
	CritChance = CritChance,
	CriticalStrike = CriticalStrike,
	Spirit = addon.Priest.Spirit,
});
