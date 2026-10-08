local name, addon = ...;

--[[----------------------------------------------------------------------------
	Utility functions
------------------------------------------------------------------------------]]
local Util = {};

-- True when `unit` carries aura `auraID` cast by the player. filter: "HELPFUL" (default) or "HARMFUL".
function Util.HasAuraFromPlayer(unit, auraID, filter)
	for i = 1, 40 do
		local _, _, source, id, blocked = addon.Compat.UnitAura(unit, i, filter);
		if blocked or not id then break end -- unreadable in combat counts as "not found"
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
	Talents - Forever serves the three Classic trees of a class as one C_Traits
	tree (one config, one tree, no tree tag on the nodes) and C_SpecializationInfo
	only knows a class-level "spec", so:
	- tab membership comes from addon.TalentTab (Parsers/Talents_Generated.lua),
	- spec = class + tab with the most points; retail spec ids are kept so
	  SpellType / SpecInfo / history keep working.
	The tree walk is cached. RebuildTalentCache runs on the talent-change events;
	the getters build the cache on first use.
------------------------------------------------------------------------------]]
local SPEC_BY_CLASS_TAB = {
	PALADIN = { [1] = 65 },
	PRIEST  = { [1] = 256, [2] = 257 },
	SHAMAN  = { [3] = 264 },
	DRUID   = { [3] = 105 },
};

local talentRanks = {};   -- name -> rank
local rankedTalents = {}; -- { {name=, icon=, rank=}, ... } with rank > 0, in tree order
local tabPoints = {};     -- tab index -> points spent
local cacheBuilt = false;

-- Calls fn(name, icon, rank) for every node of the player's trait tree. Returns false when the
-- trait data is not available yet (early in login).
local function ForEachTalent(fn)
	if not (C_ClassTalents and C_Traits) then return false end
	local configID = C_ClassTalents.GetActiveConfigID();
	local config = configID and C_Traits.GetConfigInfo(configID);
	if not config then return false end
	for _, treeID in ipairs(config.treeIDs) do
		for _, nodeID in ipairs(C_Traits.GetTreeNodes(treeID)) do
			local node = C_Traits.GetNodeInfo(configID, nodeID);
			local entryID = node and ((node.activeEntry and node.activeEntry.entryID) or node.entryIDs[1]);
			local entry = entryID and C_Traits.GetEntryInfo(configID, entryID);
			local def = entry and entry.definitionID and C_Traits.GetDefinitionInfo(entry.definitionID);
			if def and def.spellID then
				local tname, _, icon = addon.Compat.GetSpellInfo(def.spellID);
				if tname then fn(tname, icon, node.activeRank or 0) end
			end
		end
	end
	return true;
end

function Util.RebuildTalentCache()
	wipe(talentRanks); wipe(rankedTalents); wipe(tabPoints);
	local _, class = UnitClass("player");
	local tabs = addon.TalentTab and addon.TalentTab[class];
	cacheBuilt = ForEachTalent(function(tname, icon, rank)
		talentRanks[tname] = rank;
		if rank > 0 then table.insert(rankedTalents, { name = tname, icon = icon, rank = rank }) end
		local tab = tabs and tabs[tname];
		if tab then tabPoints[tab] = (tabPoints[tab] or 0) + rank end
	end);
end

local function EnsureCache()
	if not cacheBuilt then Util.RebuildTalentCache() end
end

function Util.GetSpecId()
	local _, class = UnitClass("player");
	local map = SPEC_BY_CLASS_TAB[class];
	if not map then return nil end
	EnsureCache();
	local bestTab, bestPts = nil, 0;
	for tab = 1, 3 do
		local pts = tabPoints[tab] or 0;
		if pts > bestPts then bestTab, bestPts = tab, pts end
	end
	return bestTab and map[bestTab] or nil;
end

function Util.GetTalentRank(talentName)
	EnsureCache();
	return talentRanks[talentName] or 0;
end

-- Talents with at least one point, for the history display. A fresh table every call: history
-- entries keep the one they were given across cache rebuilds.
function Util.GetTalentSnapshot()
	EnsureCache();
	local t = {};
	for _, talent in ipairs(rankedTalents) do table.insert(t, Util.CopyTable(talent)) end
	return t;
end

function addon:GetSpecId() return Util.GetSpecId() end
function addon:GetTalentRank(talentName) return Util.GetTalentRank(talentName) end

addon.Util = Util;
