local name, addon = ...;
addon.inCombat = false;
addon.currentSegment = 0;

--[[----------------------------------------------------------------------------
	Helpers
------------------------------------------------------------------------------]]
-- Mana cost of a spell right now: the client API when present (talent reductions,
-- downranks, Clearcasting), else the table value. 0 when unknown.
local function SpellManaCost(spellID, s)
	local cost = addon.Compat.GetSpellManaCost(spellID);
	if cost ~= nil then return cost end
	return s and s.manaCost or 0;
end

-- Mana a cast of the player's restores, by its tooltip: every mana potion rank reads "Restores X to
-- Y mana." (seen in game 2026-11-11: 437, 140 to 180) and the runes are worded the same way. The
-- mana gained is not readable, so the average stands in. nil while the text cannot be read; the
-- answer is kept per spell id once it can.
local restoreAmount, restoreWarned = {}, {};
local function ManaRestoredBy(spellID)
	local known = restoreAmount[spellID];
	if known then return known end
	local text = addon.Compat.GetSpellDescription(spellID);
	if not text then return nil end
	local lo, hi = text:match("^Restores (%d+) to (%d+) mana");
	restoreAmount[spellID] = lo and (tonumber(lo) + tonumber(hi)) / 2 or 0;
	return restoreAmount[spellID];
end

--[[----------------------------------------------------------------------------
	Combat / encounter boundaries
------------------------------------------------------------------------------]]
-- A combat flag is secret on Forever for a unit reached through a hostile one: not in combat then.
local function inCombat(token)
	local v = UnitAffectingCombat(token);
	if issecretvalue and issecretvalue(v) then return false end
	return v and true or false;
end

-- True while the player or any group member is in combat.
local function groupInCombat()
	if inCombat("player") then return true end
	local prefix = UnitInRaid("player") and "raid" or "party";
	for i = 1, GetNumGroupMembers() do
		if inCombat(prefix .. i) then return true end
	end
	return false;
end

-- A healer drops combat between packs while the group fights on, and the matcher drops every
-- heal outside a fight: the fight ends only once the whole group is out of combat.
local combatPoll;
local function stopCombatPoll()
	if combatPoll then combatPoll:Cancel(); combatPoll = nil end
end

function addon.hsw:PLAYER_REGEN_DISABLED()
	addon.ManaDeficit:SetDrinkRate(0); -- combat ends a drink, and buffs cannot be read from here on
	stopCombatPoll(); -- back in combat: the fight is still open, nothing to end
	addon:StartFight(nil);
	-- no combat log to name the fight from: use the hostile target we have, if any. Its name is
	-- a secret string once combat has started (then the fight stays "Trash" until the finaliser
	-- names it after its meter session).
	if addon.inCombat and UnitExists("target") and UnitCanAttack("player", "target") then
		local targetName = addon.Compat.PlainString(UnitName("target"));
		if targetName then addon.SegmentManager:SetCurrentId(targetName) end
	end
end

function addon.hsw:PLAYER_REGEN_ENABLED()
	if addon.inBossFight then return end
	if not addon.inCombat then
		-- a combat the addon did not track (content gate off): its meter sessions are nobody's
		addon.SessionTotals.Advance();
		return;
	end
	if addon.discoverSpells then
		addon:Msg("[HealerStatWeights]: player left combat, group " .. (groupInCombat() and "still fighting." or "out of combat."));
	end
	if not groupInCombat() then
		addon:EndFight();
	elseif not combatPoll then
		combatPoll = C_Timer.NewTicker(1, function()
			if not groupInCombat() then
				stopCombatPoll();
				addon:EndFight();
			end
		end);
	end
end

-- A boss pulled while a fight is open (trash, or the healer entered combat first) gets its own
-- segment: the open one is closed, so the boss is not logged under a trash name.
function addon.hsw:ENCOUNTER_START(eventName, encounterId, encounterName)
	stopCombatPoll();
	addon:EndFight();
	addon:StartFight(encounterName, true);
	addon.inBossFight = true; -- wait for ENCOUNTER_END to close the segment
end

function addon.hsw:ENCOUNTER_END()
	addon.inBossFight = false;
	if addon.discoverSpells then addon:Msg("[HealerStatWeights]: encounter ended.") end
	addon:EndFight();
end

--[[----------------------------------------------------------------------------
	Character state
------------------------------------------------------------------------------]]
local function RefreshCharacter()
	addon.Util.RebuildTalentCache();
	addon:SetupConversionFactors();
	addon:UpdateEquipment();
	addon:UpdatePlayerStats();
	addon:AdjustVisibility();
end

function addon.hsw:PLAYER_ENTERING_WORLD()
	addon.inBossFight = false; -- ENCOUNTER_END never came (zoned out mid-encounter)
	addon.SessionTotals.Advance(); -- meter sessions from before the login or zone-in are not a fight's
	addon:SetupFrame();
	RefreshCharacter();
end

function addon.hsw:CHARACTER_POINTS_CHANGED() RefreshCharacter() end
function addon.hsw:PLAYER_TALENT_UPDATE() RefreshCharacter() end
function addon.hsw:TRAIT_TREE_CURRENCY_INFO_UPDATED() RefreshCharacter() end
function addon.hsw:COMBAT_RATING_UPDATE() addon:UpdatePlayerStats() end
function addon.hsw:PLAYER_EQUIPMENT_CHANGED() addon:UpdateEquipment(); addon:UpdatePlayerStats() end

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
	-- Oath of Light is sworn before the pull and lasts 5 min, so it is marked in or out of combat.
	-- One Oath at a time: the new target takes it from the old one.
	if spellID == self.Paladin.OathOfLight then
		self.BuffTracker:UnmarkAll(spellID);
		self.BuffTracker:MarkTarget(self.HealMatcher:SentTarget(spellID), spellID, self.Paladin.OathOfLightDuration);
	end
	local s = self.Spells:Get(spellID);
	local back = s and self:CastManaReturn(s) or 0; -- every heal cast, in or out of combat: Litany of Light tracks the previous one
	if not self.inCombat then
		-- between pulls the bar still moves, and the next fight starts where it stands
		local gained = not s and ManaRestoredBy(spellID) or 0;
		if gained > 0 then self.ManaDeficit:Gain(gained) end
		local spent = SpellManaCost(spellID, s) - back;
		if spent > 0 then self.ManaDeficit:Spend(spent) end
		return;
	end
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

	-- a mana potion or rune: mana that came neither from the pool nor from regen
	if not s then
		local gained = ManaRestoredBy(spellID);
		if gained and gained > 0 then
			self.SegmentManager:ForEachLive(function(seg) seg:IncManaGained(gained) end);
			self.ManaDeficit:Gain(gained, now);
		elseif not gained and self.discoverSpells and not restoreWarned[spellID] then
			restoreWarned[spellID] = true;
			self:Msg("[HealerStatWeights]: spell " .. tostring(spellID) .. " has no readable description: a mana potion would not be counted.");
		end
	end

	-- mana: free casts, filler accounting, five-second rule
	local cost = SpellManaCost(spellID, s);
	local free = false;
	if cost > 0 then
		for buffId in pairs(self.FreeCastBuffs) do
			if self.BuffTracker:Get(buffId) > 0 then
				self.BuffTracker:Consume(buffId); -- spent by this cast
				free = true;
				break;
			end
		end
	end
	if s then self:LogEvent("cast", s, self.HealMatcher:SentTarget(spellID), nil, nil, free and 0 or cost) end
	if cost <= 0 or free then return end
	local spent = cost - back; -- Litany and set bonuses return part of the cost
	self.SegmentManager:ForEachLive(function(seg) seg:IncManaSpent(spent) end); -- heal or not, it drains the pool
	self.ManaDeficit:Spend(spent, now);
	if s and s.filler then
		self.SegmentManager:ForEachLive(function(seg) seg:IncFillerCasts(spent) end);
	end
	self.SegmentManager:ForEachLive(function(seg) seg:AccumulateFSR(now) end);
	self.lastManaSpend = now;
end

--[[----------------------------------------------------------------------------
	Unit events. Player-only except UNIT_COMBAT, which reports heals on any unit.
------------------------------------------------------------------------------]]
local function AccumulateNow()
	local now = GetTime();
	addon.ManaDeficit:Advance(now); -- in or out of combat: the bar regenerates between pulls too
	if addon.inCombat then
		addon.SegmentManager:ForEachLive(function(seg) seg:AccumulateFSR(now) end);
	end
end

local function UnitEventHandler(_, e, ...)
	if e == "UNIT_AURA" then
		addon.BuffTracker:UpdatePlayerBuffs();
		AccumulateNow();          -- credit elapsed time at the old casting-regen share (Innervate etc.)
		addon.ManaDeficit:ScanDrink();
		addon:UpdatePlayerStats();
	elseif e == "UNIT_STATS" then
		AccumulateNow();
		addon:UpdatePlayerStats();
	elseif e == "UNIT_COMBAT" then
		local unit, action, flag, amount = ...;
		addon.HealMatcher:OnUnitCombat(unit, action, flag, amount);
	elseif e == "UNIT_SPELLCAST_SENT" then
		local _, target, castGUID, spellID = ...;
		addon.HealMatcher:OnCastSent(spellID, target, nil, castGUID);
	elseif e == "UNIT_SPELLCAST_FAILED" or e == "UNIT_SPELLCAST_FAILED_QUIET" or e == "UNIT_SPELLCAST_INTERRUPTED" then
		local _, castGUID, spellID = ...;
		addon.HealMatcher:OnCastFailed(spellID, castGUID);
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
	self.frame:RegisterUnitEvent("UNIT_SPELLCAST_FAILED_QUIET", "player"); -- Forever: a queued cast sends twice, one copy fails quietly
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
