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
	-- no combat log to name the fight from: use the hostile target we have, if any
	if addon.inCombat and UnitExists("target") and UnitCanAttack("player", "target") then
		addon.SegmentManager:SetCurrentId(UnitName("target"));
	end
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
function addon.hsw:TRAIT_TREE_CURRENCY_INFO_UPDATED() RefreshCharacter() end
function addon.hsw:COMBAT_RATING_UPDATE() addon:UpdatePlayerStats() end
function addon.hsw:PLAYER_EQUIPMENT_CHANGED() addon:UpdatePlayerStats() end

function addon.hsw:GROUP_ROSTER_UPDATE()
	if addon.inCombat then -- someone joined/left mid-combat
		addon.UnitManager:Cache();
	end
end

--[[----------------------------------------------------------------------------
	Player casts (UNIT_SPELLCAST_SUCCEEDED). Forever gives addons no combat log,
	so this is where self-cast buffs, shields, the heal matcher, filler mana and
	the five-second rule are fed.
	Five-second rule: every successful cast that cost mana restarts it; time up
	to now is credited with the previous spend first. Clearcasting procs are not
	visible in combat, so only Inner Focus (our own cast) marks a free cast.
------------------------------------------------------------------------------]]
function addon:OnPlayerSpellcast(spellID)
	if not self.inCombat then return end
	local s = self.Spells:Get(spellID);
	local now = GetTime();

	-- buffs we cast ourselves are the only ones visible in combat
	if spellID == self.Shaman.WaterShield then
		self.BuffTracker:MarkCast(spellID, self.Shaman.WaterShieldDuration);
	elseif spellID == self.Priest.InnerFocus then
		self.BuffTracker:MarkCast(spellID, self.Priest.InnerFocusDuration);
	end

	-- shields are credited at cast time (absorbs are not observable)
	if self.AbsorbSpells[spellID] then
		local targetName = self.HealMatcher:SentTarget(spellID);
		local unit = self.UnitManager:FindByName(targetName);
		if unit then
			self.StatParser:DecompShieldCast(UnitGUID(unit), spellID);
			self.BuffTracker:MarkTarget(targetName, self.Priest.WeakenedSoul, self.Priest.WeakenedSoulDuration);
		end
	end

	self.HealMatcher:OnCastSucceeded(spellID, now);

	-- mana: free casts, filler accounting, five-second rule
	local cost = SpellManaCost(spellID, s);
	if cost <= 0 then return end
	for buffId in pairs(self.FreeCastBuffs) do
		if self.BuffTracker:Get(buffId) > 0 then
			self.BuffTracker:Consume(buffId); -- spent by this cast
			return;
		end
	end
	if s and s.filler then
		forEachSegment(function(seg) seg:IncFillerCasts(cost) end);
	end
	forEachSegment(function(seg) seg:AccumulateFSR(now) end);
	self.lastManaSpend = now;
end

--[[----------------------------------------------------------------------------
	Unit events. Player-only except UNIT_COMBAT, which reports heals on any unit.
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
	elseif e == "UNIT_COMBAT" then
		local unit, action, flag, amount = ...;
		addon.HealMatcher:OnUnitCombat(unit, action, flag, amount);
	elseif e == "UNIT_SPELLCAST_SENT" then
		local _, target, _, spellID = ...;
		addon.HealMatcher:OnCastSent(spellID, target);
	elseif e == "UNIT_SPELLCAST_FAILED" or e == "UNIT_SPELLCAST_INTERRUPTED" then
		local _, _, spellID = ...;
		addon.HealMatcher:OnCastFailed(spellID);
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
	self.frame:RegisterUnitEvent("UNIT_SPELLCAST_SENT", "player");
	self.frame:RegisterUnitEvent("UNIT_SPELLCAST_FAILED", "player");
	self.frame:RegisterUnitEvent("UNIT_SPELLCAST_INTERRUPTED", "player");
	self.frame:RegisterUnitEvent("UNIT_SPELLCAST_SUCCEEDED", "player");
	self.frame:RegisterEvent("UNIT_COMBAT"); -- every unit: our heals land on anyone
	self.frame:SetScript("OnEvent", UnitEventHandler);
end

--[[----------------------------------------------------------------------------
	Registration. COMBAT_LOG_EVENT_UNFILTERED is a protected action on Forever
	(ADDON_ACTION_BLOCKED) and is not registered.
------------------------------------------------------------------------------]]
addon.hsw:RegisterEvent("PLAYER_REGEN_DISABLED");
addon.hsw:RegisterEvent("PLAYER_REGEN_ENABLED");
addon.hsw:RegisterEvent("PLAYER_EQUIPMENT_CHANGED");
addon.hsw:RegisterEvent("PLAYER_ENTERING_WORLD");
addon.hsw:RegisterEvent("ENCOUNTER_START");
addon.hsw:RegisterEvent("ENCOUNTER_END");
addon.hsw:RegisterEvent("COMBAT_RATING_UPDATE");
addon.hsw:RegisterEvent("GROUP_ROSTER_UPDATE");
addon.hsw:RegisterEvent("CHARACTER_POINTS_CHANGED");
-- Registering an event name the client does not know throws. On Forever a talent point spend fires only
-- TRAIT_TREE_CURRENCY_INFO_UPDATED (probe 2026-10-07); the other two stay for respec / login paths.
pcall(addon.hsw.RegisterEvent, addon.hsw, "PLAYER_TALENT_UPDATE");
pcall(addon.hsw.RegisterEvent, addon.hsw, "TRAIT_TREE_CURRENCY_INFO_UPDATED");
