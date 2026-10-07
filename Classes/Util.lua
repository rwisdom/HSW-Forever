local name, addon = ...;

--[[----------------------------------------------------------------------------
	Utility functions
------------------------------------------------------------------------------]]
local Util = {};

-- True when `unit` carries aura `auraID` cast by the player. filter: "HELPFUL" (default) or "HARMFUL".
function Util.HasAuraFromPlayer(unit, auraID, filter)
	for i = 1, 40 do
		local _, _, source, id = addon.Compat.UnitAura(unit, i, filter);
		if not id then break end
		if source == "player" and id == auraID then return true end
	end
	return false;
end

function Util.CopyTable(t)
	local new_t = {};
	local mt = getmetatable(t);
	for k, v in pairs(t) do new_t[k] = v; end
	setmetatable(new_t, mt);
	return new_t;
end

--[[----------------------------------------------------------------------------
	Spec detection - Classic-family clients have no GetSpecialization().
	Spec = class + talent tab with the most points. Retail spec ids are kept so
	SpellType / SpecInfo / history keep working.
------------------------------------------------------------------------------]]
local SPEC_BY_CLASS_TAB = {
	PALADIN = { [1] = 65 },
	PRIEST  = { [1] = 256, [2] = 257 },
	SHAMAN  = { [3] = 264 },
	DRUID   = { [3] = 105 },
};

function Util.GetSpecId()
	local _, class = UnitClass("player");
	local map = SPEC_BY_CLASS_TAB[class];
	if not map then return nil end
	local bestTab, bestPts = nil, 0;
	for i = 1, GetNumTalentTabs() do
		local _, _, pts = GetTalentTabInfo(i);
		pts = pts or 0;
		if pts > bestPts then bestTab, bestPts = i, pts end
	end
	return bestTab and map[bestTab] or nil;
end

--[[----------------------------------------------------------------------------
	Talent rank cache - rebuilt on CHARACTER_POINTS_CHANGED / PLAYER_TALENT_UPDATE.
	GetTalentInfo(tab, i) -> name, icon, tier, column, rank, maxRank
------------------------------------------------------------------------------]]
local talentRanks = {};

function Util.RebuildTalentCache()
	wipe(talentRanks);
	for tab = 1, GetNumTalentTabs() do
		for i = 1, GetNumTalents(tab) do
			local tname, _, _, _, rank = GetTalentInfo(tab, i);
			if tname then talentRanks[tname] = rank or 0 end
		end
	end
end

function Util.GetTalentRank(talentName)
	return talentRanks[talentName] or 0;
end

-- Talents with at least one point, for the history display.
function Util.GetTalentSnapshot()
	local t = {};
	for tab = 1, GetNumTalentTabs() do
		for i = 1, GetNumTalents(tab) do
			local tname, icon, _, _, rank = GetTalentInfo(tab, i);
			if tname and rank and rank > 0 then
				table.insert(t, { name = tname, icon = icon, rank = rank });
			end
		end
	end
	return t;
end

function addon:GetSpecId() return Util.GetSpecId() end
function addon:GetTalentRank(talentName) return Util.GetTalentRank(talentName) end

addon.Util = Util;
