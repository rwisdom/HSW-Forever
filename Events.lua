local name, addon = ...;
addon.inCombat = false;
addon.currentSegment = 0;

--[[----------------------------------------------------------------------------
	Helpers
------------------------------------------------------------------------------]]
local function forEachSegment(fn)
	local cur_seg = addon.SegmentManager:Get(0);
	local ttl_seg = addon.SegmentManager:Get("Total");
	if cur_seg then fn(cur_seg) end
	if ttl_seg then fn(ttl_seg) end
end

-- Mana cost of a spell right now: the client API when present (talent reductions,
-- downranks, Clearcasting), else the table value. 0 when unknown.
local function SpellManaCost(spellID, s)
	local cost = addon.Compat.GetSpellManaCost(spellID);
	if cost ~= nil then return cost end
	return s and s.manaCost or 0;
end

--[[----------------------------------------------------------------------------
	Combat / encounter boundaries
------------------------------------------------------------------------------]]
function addon.hsw:PLAYER_REGEN_DISABLED()
	addon:StartFight(nil);
end

function addon.hsw:PLAYER_REGEN_ENABLED()
	if not addon.inBossFight then
		addon:EndFight();
	end
end

function addon.hsw:ENCOUNTER_START(eventName, encounterId, encounterName)
	addon:StartFight(encounterName);
	addon.inBossFight = true; -- wait for ENCOUNTER_END to close the segment
end

function addon.hsw:ENCOUNTER_END()
	addon.inBossFight = false;
	addon:EndFight();
end

--[[----------------------------------------------------------------------------
	Character state
------------------------------------------------------------------------------]]
local function RefreshCharacter()
	addon.Util.RebuildTalentCache();
	addon:SetupConversionFactors();
	addon:UpdatePlayerStats();
	addon:AdjustVisibility();
end

function addon.hsw:PLAYER_ENTERING_WORLD()
	addon.Util.RebuildTalentCache();
	addon:SetupConversionFactors();
	addon:UpdatePlayerStats();
	addon:SetupFrame();
	addon:AdjustVisibility();
end

function addon.hsw:CHARACTER_POINTS_CHANGED() RefreshCharacter() end
function addon.hsw:PLAYER_TALENT_UPDATE() RefreshCharacter() end
function addon.hsw:COMBAT_RATING_UPDATE() addon:UpdatePlayerStats() end
function addon.hsw:PLAYER_EQUIPMENT_CHANGED() addon:UpdatePlayerStats() end

function addon.hsw:GROUP_ROSTER_UPDATE()
	if addon.inCombat then -- someone joined/left mid-combat
		addon.UnitManager:Cache();
	end
end

--[[----------------------------------------------------------------------------
	COMBAT_LOG_EVENT_UNFILTERED
------------------------------------------------------------------------------]]
local summons = {};
local reportedEnergize = {};

function addon.hsw:COMBAT_LOG_EVENT_UNFILTERED()
	if not addon.inCombat then return end
	local _, ev, _, sourceGUID, sourceName, _, _, destGUID, destName, _, _, spellID, _, _, amount, overhealing, _, critFlag, arg19, _, _, arg22 = CombatLogGetCurrentEventInfo();
	local playerGUID = UnitGUID("player");

	if sourceGUID == playerGUID then
		if ev == "SPELL_CAST_SUCCESS" then
			local s = addon.Spells:Get(spellID);
			if s and s.filler then
				local cost = SpellManaCost(spellID, s);
				if cost > 0 then
					forEachSegment(function(seg) seg:IncFillerCasts(cost) end);
				end
			end
		elseif ev == "SPELL_SUMMON" then
			summons[destGUID] = true; -- totems heal from their own GUID
		end
	end

	if ev == "SPELL_HEAL" or ev == "SPELL_PERIODIC_HEAL" then
		if sourceGUID == playerGUID or summons[sourceGUID] then
			addon.StatParser:DecompHealingForCurrentSpec(ev, destGUID, spellID, critFlag, amount - overhealing, overhealing);
		end
	elseif ev == "SPELL_ENERGIZE" then
		if destGUID == playerGUID then
			if addon.ManaReturnSpells[spellID] then
				forEachSegment(function(seg) seg:IncManaRestore(amount) end);
			elseif addon.discoverSpells and not reportedEnergize[spellID] then
				-- "/hsw discover on": find Water Shield / Mana Tide / Litany of Light energize ids (Task 17)
				reportedEnergize[spellID] = true;
				addon:Msg("[HealerStatWeights]: mana return " .. tostring(spellID) .. " (" .. tostring(addon.Compat.GetSpellInfo(spellID)) .. ") is not tracked; +" .. tostring(amount) .. " mana.");
			end
		end
	elseif ev == "SPELL_ABSORBED" then
		local absorberGUID, absorbSpellID, absorbAmount;
		if type(spellID) == "number" then
			-- absorbed a spell: args 12-14 are that spell; absorber GUID 15, absorb spell 19, amount 22
			absorberGUID, absorbSpellID, absorbAmount = amount, arg19, arg22;
		else
			-- absorbed a melee swing: absorber GUID 12, absorb spell 16, amount 19
			absorberGUID, absorbSpellID, absorbAmount = spellID, overhealing, arg19;
		end
		if absorberGUID == playerGUID and addon.AbsorbSpells[absorbSpellID] then
			addon.StatParser:DecompAbsorb(destGUID, absorbSpellID, absorbAmount);
		end
	elseif ev == "SWING_DAMAGE" or ev == "SPELL_DAMAGE" or ev == "SPELL_PERIODIC_DAMAGE" then
		-- name the segment after the first enemy that hits us or that we hit
		local segment = addon.SegmentManager:Get(0);
		if segment and not segment.nameSet and sourceGUID and destGUID then
			local src_str, dest_str = string.lower(sourceGUID), string.lower(destGUID);
			local srcIsUs = src_str:find("player") or src_str:find("pet");
			local destIsUs = dest_str:find("player") or dest_str:find("pet");
			if srcIsUs and not destIsUs then
				addon.SegmentManager:SetCurrentId(destName);
			elseif destIsUs and not srcIsUs then
				addon.SegmentManager:SetCurrentId(sourceName);
			end
		end
	end
end

--[[----------------------------------------------------------------------------
	Five-second rule: every successful cast that cost mana restarts it.
	Time up to now is credited with the previous spend first.
	Approximation: a free-cast buff (Inner Focus, Clearcasting) consumed by this
	very cast may already be gone when UNIT_SPELLCAST_SUCCEEDED fires; the cost
	API (when present) still reports 0 in that case.
------------------------------------------------------------------------------]]
function addon:OnPlayerSpellcast(spellID)
	if not self.inCombat then return end
	local cost = SpellManaCost(spellID, self.Spells:Get(spellID));
	if cost <= 0 then return end
	for buffId in pairs(self.FreeCastBuffs) do
		if self.BuffTracker:Get(buffId) > 0 then return end
	end
	local now = GetTime();
	forEachSegment(function(seg) seg:AccumulateFSR(now) end);
	self.lastManaSpend = now;
end

--[[----------------------------------------------------------------------------
	Unit events (player only)
------------------------------------------------------------------------------]]
local function AccumulateNow()
	if addon.inCombat then
		local now = GetTime();
		forEachSegment(function(seg) seg:AccumulateFSR(now) end);
	end
end

local function UnitEventHandler(_, e, ...)
	if e == "UNIT_AURA" then
		addon.BuffTracker:UpdatePlayerBuffs();
		AccumulateNow();          -- credit elapsed time at the old casting-regen share (Innervate etc.)
		addon:UpdatePlayerStats();
	elseif e == "UNIT_STATS" then
		AccumulateNow();
		addon:UpdatePlayerStats();
	elseif e == "UNIT_SPELLCAST_START" then
		addon.CastTracker:StartCast(...);
	elseif e == "UNIT_SPELLCAST_SUCCEEDED" then
		local _, _, spellID = ...;
		addon.CastTracker:FinishCast(...);
		addon:OnPlayerSpellcast(spellID);
	end
end

function addon:SetupUnitEvents()
	self.frame:RegisterUnitEvent("UNIT_AURA", "player");
	self.frame:RegisterUnitEvent("UNIT_STATS", "player");
	self.frame:RegisterUnitEvent("UNIT_SPELLCAST_START", "player");
	self.frame:RegisterUnitEvent("UNIT_SPELLCAST_SUCCEEDED", "player");
	self.frame:SetScript("OnEvent", UnitEventHandler);
end

--[[----------------------------------------------------------------------------
	Registration
------------------------------------------------------------------------------]]
addon.hsw:RegisterEvent("PLAYER_REGEN_DISABLED");
addon.hsw:RegisterEvent("PLAYER_REGEN_ENABLED");
addon.hsw:RegisterEvent("PLAYER_EQUIPMENT_CHANGED");
addon.hsw:RegisterEvent("PLAYER_ENTERING_WORLD");
addon.hsw:RegisterEvent("COMBAT_LOG_EVENT_UNFILTERED");
addon.hsw:RegisterEvent("ENCOUNTER_START");
addon.hsw:RegisterEvent("ENCOUNTER_END");
addon.hsw:RegisterEvent("COMBAT_RATING_UPDATE");
addon.hsw:RegisterEvent("GROUP_ROSTER_UPDATE");
addon.hsw:RegisterEvent("CHARACTER_POINTS_CHANGED");
-- Registering an event name the client does not know throws; PLAYER_TALENT_UPDATE is not guaranteed on a 1.x client.
pcall(addon.hsw.RegisterEvent, addon.hsw, "PLAYER_TALENT_UPDATE");
