local name, addon = ...;

--[[----------------------------------------------------------------------------
	HealMatcher - attributes healing to the player's casts without a combat log.
	Forever closes COMBAT_LOG_EVENT_UNFILTERED to addons. What is left:
	  UNIT_SPELLCAST_SENT       what we cast and on whom (target name)
	  UNIT_SPELLCAST_SUCCEEDED  the cast finished
	  UNIT_COMBAT               a unit was healed: crit flag, no source, no spell; the amount is
	                            a secret value on the release client (the session totals price it)
	Direct heals: a landing expectation opens at SENT for the cast target (any unit
	for multi-target spells) and is matched to the next heal on that unit. The heal of
	a spell with a cast time lands as the cast ends, so a heal that comes while the cast
	is in flight is held until the cast's end is heard of, and was not its heal otherwise.
	HoT ticks: registered at SUCCEEDED per target (or per group member) and matched
	to later heals on that unit by the tick that is due.
	Jumps (Earthfury Healing Wave): land on other units in the frame of the main heal,
	before or after it in event order. A heal that could be a jump is held until the
	frame's main heal lands; held heals from any other frame were not ours.
	Healing Stream Totem: a heal nothing else explains while the totem is down.
	Heals from other healers cannot be told apart; the windows keep that noise small.
------------------------------------------------------------------------------]]
local HealMatcher = {};
local LANDING_WINDOW = 1.0;             -- seconds after a cast's end in which its direct heal must land
local LATE_CAST = 2.0;                  -- seconds past its cast time a cast may end (lag, pushback) and keep its expectation
local SEEN_WINDOW = 1.0;                -- how long dedupe keys are kept
local TICK_WINDOW = 0.5;                -- seconds a HoT tick may land off its due time
local HOLD_WINDOW = 0.25;               -- seconds a heal waits for the end of a cast in flight on its unit
local TOTEM = "Healing Stream Totem";

local expectations = {}; -- { spellID=, target=, remaining=, jumps=, ready=, succeeded=, landed=, expires= }, newest last
local sentTarget = {};   -- spellID -> target name of the last UNIT_SPELLCAST_SENT
local hots = {};         -- unit name -> { [spellID] = { nextTick=, interval=, expires= } }
local totem = nil;       -- { spellID=, expires= } while our totem is down
local seen = {};         -- "guid:amount" -> time of the last heal attributed or held with that key
local held = {};         -- heals that wait: { guid=, unitName=, crit=, at=, cast= }. cast: for the end of a cast in
                         -- flight on the unit (HOLD_WINDOW); else a heal of the current frame that may be a jump

local function playerName() return UnitName("player") end

-- Every Forever character has a surname: UNIT_SPELLCAST_SENT names the target "Hop Bam" where
-- UnitName gives "Hop". First names never contain a space or hyphen, so the first word is the
-- name UnitName reports.
local function bareName(n)
	n = n and n:match("^[^%s%-]+");
	return n ~= "" and n or nil;
end

-- A fight starts. The totem stays: one dropped before the pull heals through it (seen in game
-- 2026-11-21: every tick of such a fight read "unattributed heal").
function HealMatcher:Reset()
	wipe(expectations); wipe(sentTarget); wipe(hots); wipe(seen); wipe(held);
end

-- A water totem of the player's went down, in or out of combat (Events.lua): Healing Stream Totem
-- heals from now on; any other takes its place, since one water totem stands at a time.
function HealMatcher:OnWaterTotem(spellID, now)
	local s = addon.Spells:Get(spellID);
	totem = s and s.name == TOTEM and { spellID = spellID, expires = (now or GetTime()) + s.duration } or nil;
end

local function unattributed(unitName)
	addon:Discover("unattributed heal on " .. unitName .. ".");
end

local function credit(ev, guid, spellID, crit)
	addon.StatParser:DecompHealingForCurrentSpec(ev, guid, spellID, crit);
end

-- Target name of the last UNIT_SPELLCAST_SENT for a spell (the player when none).
function HealMatcher:SentTarget(spellID)
	return sentTarget[spellID] or playerName();
end

-- Who a cast with a secret target name went to, by name: the group pet under the mouse (a mouseover
-- macro heals it with another unit selected, Razorfen Kraul 2026-11-16), else the group member or
-- group pet the player has selected; nil for neither. A member under the mouse is not it: a
-- player's name is plain.
local function secretTarget()
	for _, unit in ipairs({ "mouseover", "target" }) do
		local guid = addon.Compat.PlainString(UnitGUID(unit));
		local token = guid and addon.UnitManager:Find(guid);
		if token and (unit == "target" or token:find("pet")) then
			return addon.Compat.PlainString(UnitName(token));
		end
	end
end

-- What secretTarget had to go on, for the discover line: "using Hop" for a pet healed by mouseover
-- (The Underbelly 2026-11-19) does not say whether the GUID was secret or the pet missing from the cache.
local function heldBy(unit)
	local raw = UnitGUID(unit);
	local guid = addon.Compat.PlainString(raw);
	if not guid then return unit .. (type(raw) == "string" and " secret" or " none") end -- a secret is only asked its type, as in PlainString
	return unit .. " " .. (addon.UnitManager:Find(guid) or guid:match("^[^-]+") .. " not in the group");
end

-- UNIT_SPELLCAST_SENT: targetName is "" for self casts and totems. In a dungeon the client hands
-- it over as a secret string that cannot be read: then the pet under the mouse or the selected
-- group member, else the player.
-- The target is remembered out of combat too (Oath of Light is sworn before the pull); expectations
-- open only in a fight.
function HealMatcher:OnCastSent(spellID, targetName, now, castGUID)
	local s = addon.Spells:Get(spellID);
	local plain = addon.Compat.PlainString(targetName);
	if plain or targetName == nil then
		targetName = bareName(plain) or playerName();
	else
		targetName = secretTarget() or playerName();
		if s then -- a hostile target's name is secret too: say nothing for attacks
			addon:Discover("secret cast target for spell " .. tostring(spellID) .. ", using " .. targetName
				.. " (" .. heldBy("mouseover") .. ", " .. heldBy("target") .. ").");
		end
	end
	sentTarget[spellID] = targetName;
	if not addon.inCombat then return end
	if not s or addon.AbsorbSpells[spellID] then return end -- shields are credited at cast (Events.lua)
	now = now or GetTime();
	local direct = (s.coeff > 0 or s.base > 0 or s.tick == 0) and s.name ~= TOTEM;
	if direct then
		table.insert(expectations, {
			spellID = spellID, target = targetName, remaining = s.targets, castGUID = castGUID,
			ready = s.castTime <= 0, -- an instant lands at once; a cast when it ends (OnCastSucceeded)
			jumps = addon:CastJumps(s), expires = now + math.max(s.castTime, 0) + LATE_CAST,
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

-- Our HoT on unitName with a tick due now, nearest first; its next tick moves one interval on.
-- Due means within TICK_WINDOW of the tick grid (so a tick lost to another match does not lose the
-- HoT).
local function takeHotTick(unitName, now)
	local byId = hots[unitName];
	if not byId then return nil end
	local bestId, bestDist;
	for id, h in pairs(byId) do
		local phase = (now - h.nextTick) % h.interval;
		local dist = math.min(phase, h.interval - phase);
		if dist <= TICK_WINDOW and (not bestDist or dist < bestDist) then bestId, bestDist = id, dist end
	end
	if bestId then byId[bestId].nextTick = now + byId[bestId].interval end
	return bestId;
end

-- A held heal that nothing claimed. One that waited for a cast's end was not that cast's: it is a
-- tick of ours that was due when it landed, else the totem's, else someone else's. One that might
-- have been a jump was tried as a tick before it was held.
local function settleLate(h)
	local tick = h.cast and takeHotTick(h.unitName, h.at);
	if tick then
		credit("SPELL_PERIODIC_HEAL", h.guid, tick, h.crit);
	elseif totem and totem.expires >= h.at then
		credit("SPELL_PERIODIC_HEAL", h.guid, totem.spellID, h.crit);
	else
		unattributed(h.unitName);
	end
end

-- Held heals whose wait is over: a possible jump of an earlier frame (no main heal landed with it),
-- a heal that waited HOLD_WINDOW for a cast to end.
local function expireHeld(now)
	local keep = {};
	for _, h in ipairs(held) do
		if h.at < now - (h.cast and HOLD_WINDOW or 0) then settleLate(h) else keep[#keep + 1] = h end
	end
	wipe(held);
	for i, h in ipairs(keep) do held[i] = h end
end

local function expire(now)
	for i = #expectations, 1, -1 do
		if expectations[i].expires < now then table.remove(expectations, i) end
	end
	expireHeld(now);
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

-- Whether expectation e can land on unitName (multi-target spells land anywhere).
local function fits(e, unitName)
	local s = addon.Spells:Get(e.spellID);
	return s and not e.landed and (s.targets > 1 or e.target == unitName);
end

-- One heal of e (expectations[idx]) has landed. Returns e when that was the main heal of a jumping
-- spell: its jumps come in this frame.
local function land(e, idx, now)
	e.remaining = e.remaining - 1;
	if e.remaining > 0 then return nil end
	if e.jumps > 0 then
		e.landed, e.expires = now, now; -- jumps still arrive this frame, none later
		return e;
	end
	table.remove(expectations, idx);
	return nil;
end

-- The expectation due soonest that can land on unitName now: an instant's, or a cast's whose end
-- has been heard of. A queued cast is sent before the previous one lands, so the newest is rarely
-- the one landing. Returns the spell id and, when the heal was the main heal of a jumping spell,
-- its expectation.
local function takeExpectation(unitName, now)
	local best, bestIdx;
	for i, e in ipairs(expectations) do
		if e.ready and fits(e, unitName) and (not best or e.expires < best.expires) then
			best, bestIdx = e, i;
		end
	end
	if not best then return nil end
	return best.spellID, land(best, bestIdx, now);
end

-- A cast that could land on unitName is still in flight: its heal comes as it ends, not before.
local function awaited(unitName)
	for _, e in ipairs(expectations) do
		if not e.ready and fits(e, unitName) then return true end
	end
	return false;
end

-- A jump of the spell whose main heal landed this frame on another unit.
local function takeJump(unitName, now)
	for _, e in ipairs(expectations) do
		if e.landed == now and e.jumps > 0 and e.target ~= unitName then
			e.jumps = e.jumps - 1;
			return e.spellID;
		end
	end
end

-- A jumping cast on another unit is still in flight: a heal on unitName may be one of its jumps.
local function mayJump(unitName)
	for _, e in ipairs(expectations) do
		if not e.landed and e.jumps > 0 and e.target ~= unitName then return true end
	end
	return false;
end

-- The main heal of e has just landed: the heals held this frame as possible jumps are its jumps
-- on other units. Heals that wait for a cast's end stay held.
local function creditHeld(e)
	local keep = {};
	for _, h in ipairs(held) do
		if h.cast then
			keep[#keep + 1] = h;
		elseif e.jumps > 0 and h.unitName ~= e.target then
			e.jumps = e.jumps - 1;
			credit("SPELL_HEAL", h.guid, e.spellID, h.crit);
		else
			unattributed(h.unitName);
		end
	end
	wipe(held);
	for i, h in ipairs(keep) do held[i] = h end
end

-- The cast of e (expectations[idx]) has just ended: the heals held for a cast's end on a unit it
-- can land on were its own, the newest first (one that landed a moment earlier is a tick).
local function settleHeld(e, idx, now)
	local landed;
	for i = #held, 1, -1 do
		local h = held[i];
		if h.cast and fits(e, h.unitName) then
			table.remove(held, i);
			credit("SPELL_HEAL", h.guid, e.spellID, h.crit);
			landed = land(e, idx, now);
			if e.remaining <= 0 then break end
		end
	end
	if landed then creditHeld(landed) end
end

-- UNIT_SPELLCAST_SUCCEEDED: the cast finished now. Its heal lands in this frame, before or after
-- this event (seen in game 2026-11-21: the heal first), or shortly after: the oldest pending
-- expectation of the spell may be taken from now on, takes the heals held for it and gets a fresh
-- landing window (spell pushback stretches a cast past the one opened at SENT). The periodic parts
-- start now.
function HealMatcher:OnCastSucceeded(spellID, now)
	if not addon.inCombat then return end
	local s = addon.Spells:Get(spellID);
	if not s then return end
	now = now or GetTime();
	expireHeld(now);
	for i, e in ipairs(expectations) do
		if e.spellID == spellID and not e.landed and not e.succeeded then
			e.succeeded, e.ready = now, true;
			e.expires = math.max(e.expires, now + LANDING_WINDOW);
			settleHeld(e, i, now);
			break;
		end
	end
	if s.name == TOTEM then
		self:OnWaterTotem(spellID, now);
	elseif s.tick > 0 and s.duration > 0 then
		registerHot(s, sentTarget[spellID] or playerName(), now);
	end
end

-- UNIT_COMBAT(unitToken, action, flag, amount, school). The amount is a secret value on the
-- release client and is not read: the heal is counted, the session totals price it at fight end.
function HealMatcher:OnUnitCombat(unitToken, action, flag, amount, now)
	if action ~= "HEAL" or not addon.inCombat then return end
	-- secret in combat for a unit reached through a hostile one ("targettarget"): drop it, the
	-- same heal also arrives on the unit's own group token.
	local P = addon.Compat.PlainString;
	local guid, unitName = P(UnitGUID(unitToken)), P(UnitName(unitToken));
	if not guid or not unitName then return end
	now = now or GetTime();
	local crit = flag == "CRITICAL";

	-- one heal arrives once per unit token that points at the unit: same unit, crit flag and frame.
	-- Two different heals on one unit in one frame with the same flag merge into one count.
	-- Only attributed and held heals are remembered, so an unattributed heal never shadows a later one.
	local key = guid .. ":" .. (crit and "1" or "0");
	if seen[key] == now then return end
	expire(now);

	local ev, spellID, landed = "SPELL_HEAL", takeExpectation(unitName, now);
	if not spellID and awaited(unitName) then
		-- a cast on this unit is in flight: its heal if the cast ends now, a tick or someone else's if not
		seen[key] = now;
		table.insert(held, { guid = guid, unitName = unitName, crit = crit, at = now, cast = true });
		return;
	end
	if not spellID then
		ev, spellID = "SPELL_PERIODIC_HEAL", takeHotTick(unitName, now);
	end
	if not spellID then
		ev, spellID = "SPELL_HEAL", takeJump(unitName, now);
	end
	if not spellID and mayJump(unitName) then
		seen[key] = now;
		table.insert(held, { guid = guid, unitName = unitName, crit = crit, at = now });
		return;
	end
	if not spellID and totem then
		ev, spellID = "SPELL_PERIODIC_HEAL", totem.spellID;
	end
	if not spellID then
		unattributed(unitName);
		return;
	end
	seen[key] = now;
	credit(ev, guid, spellID, crit);
	if landed then creditHeld(landed) end
end

-- The fight is over (addon:EndFight): heals still held are settled as they stand.
function HealMatcher:Flush()
	for _, h in ipairs(held) do settleLate(h) end
	wipe(held);
end

addon.HealMatcher = HealMatcher;
