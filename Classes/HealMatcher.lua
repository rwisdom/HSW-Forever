local name, addon = ...;

--[[----------------------------------------------------------------------------
	HealMatcher - attributes healing to the player's casts without a combat log.
	Forever closes COMBAT_LOG_EVENT_UNFILTERED to addons. What is left:
	  UNIT_SPELLCAST_SENT       what we cast and on whom (target name)
	  UNIT_SPELLCAST_SUCCEEDED  the cast finished
	  UNIT_COMBAT               a unit was healed: amount and crit flag, no source, no spell
	Direct heals: a landing expectation opens at SENT for the cast target (any unit
	for multi-target spells) and is matched to the next heal on that unit.
	HoT ticks: registered at SUCCEEDED per target (or per group member) and matched
	to later heals on that unit by the tick that is due.
	Healing Stream Totem: a heal nothing else explains while the totem is down.
	Heals from other healers cannot be told apart; the windows keep that noise small.
------------------------------------------------------------------------------]]
local HealMatcher = {};
local LANDING_WINDOW = 1.0;             -- seconds after the cast time in which a direct heal must land
local SEEN_WINDOW = 1.0;                -- how long dedupe keys are kept
local TOTEM = "Healing Stream Totem";

local expectations = {}; -- { spellID=, target=, remaining=, expires= }, newest last
local sentTarget = {};   -- spellID -> target name of the last UNIT_SPELLCAST_SENT
local hots = {};         -- unit name -> { [spellID] = { nextTick=, interval=, expires= } }
local totem = nil;       -- { spellID=, expires= } while our totem is down
local seen = {};         -- "guid:amount" -> time of the last heal attributed with that key

local function playerName() return UnitName("player") end

-- Every Forever character has a surname: UNIT_SPELLCAST_SENT names the target "Hop Bam" where
-- UnitName gives "Hop". First names never contain a space or hyphen, so the first word is the
-- name UnitName reports.
local function bareName(n)
	n = n and n:match("^[^%s%-]+");
	return n ~= "" and n or nil;
end

function HealMatcher:Reset()
	wipe(expectations); wipe(sentTarget); wipe(hots); wipe(seen);
	totem = nil;
end

-- Target name of the last UNIT_SPELLCAST_SENT for a spell (the player when none).
function HealMatcher:SentTarget(spellID)
	return sentTarget[spellID] or playerName();
end

-- The group member the player has selected, by name; nil for no target, a hostile one or a stranger.
local function selectedGroupMember()
	local guid = addon.Compat.PlainString(UnitGUID("target"));
	local token = guid and addon.UnitManager:Find(guid);
	return token and addon.Compat.PlainString(UnitName(token)) or nil;
end

-- UNIT_SPELLCAST_SENT: targetName is "" for self casts and totems. In a dungeon the client hands
-- it over as a secret string that cannot be read: then the selected group member, else the player.
function HealMatcher:OnCastSent(spellID, targetName, now, castGUID)
	if not addon.inCombat then return end
	local plain = addon.Compat.PlainString(targetName);
	if plain or targetName == nil then
		targetName = bareName(plain) or playerName();
	else
		targetName = selectedGroupMember() or playerName();
		if addon.discoverSpells then
			addon:Msg("[HealerStatWeights]: secret cast target for spell " .. tostring(spellID) .. ", using " .. targetName .. ".");
		end
	end
	sentTarget[spellID] = targetName;
	local s = addon.Spells:Get(spellID);
	if not s or addon.AbsorbSpells[spellID] then return end -- shields are credited at cast (Events.lua)
	now = now or GetTime();
	local direct = (s.coeff > 0 or s.base > 0 or s.tick == 0) and s.name ~= TOTEM;
	if direct then
		table.insert(expectations, {
			spellID = spellID, target = targetName, remaining = s.targets, castGUID = castGUID,
			expires = now + math.max(s.castTime, 0) + LANDING_WINDOW,
		});
	end
end

-- UNIT_SPELLCAST_FAILED / UNIT_SPELLCAST_INTERRUPTED: that cast's expectation goes (the newest
-- for the spell when no cast GUID is given). Forever repeats INTERRUPTED for one cast.
function HealMatcher:OnCastFailed(spellID, castGUID)
	for i = #expectations, 1, -1 do
		local e = expectations[i];
		if castGUID and e.castGUID == castGUID or not castGUID and e.spellID == spellID then
			table.remove(expectations, i);
			return;
		end
	end
end

local function registerHot(s, targetName, now)
	local function add(unitName)
		hots[unitName] = hots[unitName] or {};
		hots[unitName][s.spellID] = { nextTick = now + s.tick, interval = s.tick, expires = now + s.duration + s.tick };
	end
	if s.party then
		for _, unitName in ipairs(addon.UnitManager:GroupNames()) do add(unitName) end
	else
		add(targetName);
	end
end

-- UNIT_SPELLCAST_SUCCEEDED: periodic parts start now.
function HealMatcher:OnCastSucceeded(spellID, now)
	if not addon.inCombat then return end
	local s = addon.Spells:Get(spellID);
	if not s then return end
	now = now or GetTime();
	if s.name == TOTEM then
		totem = { spellID = spellID, expires = now + s.duration };
	elseif s.tick > 0 and s.duration > 0 then
		registerHot(s, sentTarget[spellID] or playerName(), now);
	end
end

local function expire(now)
	for i = #expectations, 1, -1 do
		if expectations[i].expires < now then table.remove(expectations, i) end
	end
	for unitName, byId in pairs(hots) do
		for id, h in pairs(byId) do
			if h.expires < now then byId[id] = nil end
		end
		if next(byId) == nil then hots[unitName] = nil end
	end
	if totem and totem.expires < now then totem = nil end
	for key, t in pairs(seen) do
		if now - t > SEEN_WINDOW then seen[key] = nil end
	end
end

-- The expectation due soonest that can land on unitName (multi-target spells land anywhere).
-- A queued cast is sent before the previous one lands, so the newest is rarely the one landing.
local function takeExpectation(unitName)
	local best, bestIdx;
	for i, e in ipairs(expectations) do
		local s = addon.Spells:Get(e.spellID);
		if (e.target == unitName or (s and s.targets > 1)) and (not best or e.expires < best.expires) then
			best, bestIdx = e, i;
		end
	end
	if not best then return nil end
	best.remaining = best.remaining - 1;
	if best.remaining <= 0 then table.remove(expectations, bestIdx) end
	return best.spellID;
end

-- Our HoT on unitName whose tick is nearest to now; its next tick moves one interval on.
local function takeHotTick(unitName, now)
	local byId = hots[unitName];
	if not byId then return nil end
	local bestId, bestDist;
	for id, h in pairs(byId) do
		local dist = math.abs(now - h.nextTick);
		if not bestDist or dist < bestDist then bestId, bestDist = id, dist end
	end
	if bestId then byId[bestId].nextTick = now + byId[bestId].interval end
	return bestId;
end

-- UNIT_COMBAT(unitToken, action, flag, amount, school)
function HealMatcher:OnUnitCombat(unitToken, action, flag, amount, now)
	if action ~= "HEAL" or not addon.inCombat then return end
	amount = addon.Compat.PlainNumber(amount);
	if not amount or amount <= 0 then return end
	-- secret in combat for a unit reached through a hostile one ("targettarget"): drop it, the
	-- same heal also arrives on the unit's own group token.
	local P = addon.Compat.PlainString;
	local guid, unitName = P(UnitGUID(unitToken)), P(UnitName(unitToken));
	if not guid or not unitName then return end
	now = now or GetTime();

	-- one heal arrives once per unit token that points at the unit: same unit, amount and frame.
	-- Only attributed heals are remembered, so an unattributed heal never shadows a later one.
	local key = guid .. ":" .. amount;
	if seen[key] == now then return end
	expire(now);

	local ev, spellID = "SPELL_HEAL", takeExpectation(unitName);
	if not spellID then
		ev, spellID = "SPELL_PERIODIC_HEAL", takeHotTick(unitName, now);
	end
	if not spellID and totem then
		spellID = totem.spellID;
	end
	if not spellID then
		if addon.discoverSpells then
			addon:Msg("[HealerStatWeights]: unattributed heal of " .. tostring(amount) .. " on " .. unitName .. ".");
		end
		return;
	end
	seen[key] = now;
	addon.StatParser:DecompHealingForCurrentSpec(ev, guid, spellID, flag == "CRITICAL", amount, 0);
end

addon.HealMatcher = HealMatcher;
