local name, addon = ...;

--[[----------------------------------------------------------------------------
	SessionTotals - the player's per-spell healing from Blizzard's damage meter.
	On the release client every UNIT_COMBAT heal amount is a secret value; the meter's
	session totals are the one readable amount source. They are secret in combat and
	plain once the client releases them, so Read returns nil until then and the
	caller polls (addon:FinalizePending). The meter opens one session per fight on
	its own terms; a HealerStatWeights segment sums the sessions opened while it ran.
	Field names seen in game 2026-11-07: sessions { sessionID, name, durationSeconds },
	a source { combatSpells = { { spellID, totalAmount, overkillAmount } }, totalAmount }.
	Overheal is not recorded (a fully overhealed cast creates no source at all).
------------------------------------------------------------------------------]]
local SessionTotals = {};

-- Newest session id seen at an out-of-combat moment: login, a fight priced, an untracked combat
-- over. The meter opens a fight's session before PLAYER_REGEN_DISABLED reaches the addon (seen in
-- a dungeon 2026-11-07), so a fight cannot read "newest" at its start: every session above the
-- watermark belongs to the fight running or starting.
SessionTotals.watermark = 0;

-- The last session read and the player's per-spell totals in it at that moment. The meter keeps a
-- session open across a short gap between pulls (Blackfathom Deeps 2026-11-13: same id, a longer
-- duration), so healing lands in a session after a fight has read it.
local taken = {};

local function healingDone()
	return Enum and Enum.DamageMeterType and Enum.DamageMeterType.HealingDone or 2;
end

-- Highest session id: 0 without the API or without sessions, nil while the list cannot be read
-- (secret ids in combat). Callers keep a watermark for the nil case.
function SessionTotals.Newest()
	if not C_DamageMeter or not C_DamageMeter.GetAvailableCombatSessions then return 0 end
	local P = addon.Compat.PlainNumber;
	local ok, sessions = pcall(C_DamageMeter.GetAvailableCombatSessions);
	if not ok then return nil end
	local newest = 0;
	for _, s in ipairs(sessions or {}) do
		local id = P(s.sessionID);
		if not id then return nil end
		if id > newest then newest = id end
	end
	return newest;
end

-- Raise the watermark to `id`. Without one, set it to the newest readable session: an out-of-combat
-- reading below the watermark means the meter restarted its ids (Deadmines 2026-11-10: 10 -> 7).
-- A newest session other than the one last read is an untracked fight's or a restarted id: what
-- was read no longer says anything about the session a fight will start on.
function SessionTotals.Advance(id)
	local newest = not id and SessionTotals.Newest();
	if newest then
		SessionTotals.watermark = newest;
		if taken.id ~= newest then taken = {} end
	elseif id and id > SessionTotals.watermark then
		SessionTotals.watermark = id;
	end
end

-- Lower the watermark to `id`: a fight was priced below its start, so the meter restarted its ids
-- since the watermark was read.
function SessionTotals.Restart(id)
	SessionTotals.watermark = id;
end

-- { [spellID] = amount } for the player in one session; nil while a value is secret.
local function session(id)
	local P = addon.Compat.PlainNumber;
	local totals = {};
	-- nil: no session with that id, or the player healed nothing in it
	local source = C_DamageMeter.GetCombatSessionSourceFromID(id, healingDone(), UnitGUID("player"));
	for _, spell in ipairs(source and source.combatSpells or {}) do
		local spellID, amount = P(spell.spellID), P(spell.totalAmount);
		if not spellID or not amount then return nil end
		totals[spellID] = amount;
	end
	return totals;
end

-- The range starts on a session already read (`from`): it gives what it gained since, or nothing
-- when the reading was not ours. Returns the totals and the last session's own.
local function read(from, to)
	local totals, last = {}, nil;
	for id = from, to do
		last = session(id);
		if not last then return nil end
		local before = id == from and (taken.id == id and taken.totals or last) or {};
		for spellID, amount in pairs(last) do
			local gained = amount - (before[spellID] or 0);
			if gained > 0 then totals[spellID] = (totals[spellID] or 0) + gained end
		end
	end
	return totals, last;
end

-- Name of the longest session with from < id <= to (the mob the meter named it after); nil when
-- none is in range or a value is still secret. Names a fight whose hostile target was secret.
function SessionTotals.Name(from, to)
	if not C_DamageMeter or not C_DamageMeter.GetAvailableCombatSessions then return nil end
	local P, S = addon.Compat.PlainNumber, addon.Compat.PlainString;
	local ok, sessions = pcall(C_DamageMeter.GetAvailableCombatSessions);
	if not ok then return nil end
	local best, bestDuration;
	for _, s in ipairs(sessions or {}) do
		local id = P(s.sessionID);
		if id and id > from and id <= to then
			local sname, duration = S(s.name), P(s.durationSeconds) or 0;
			if sname and sname ~= "" and (not bestDuration or duration > bestDuration) then
				best, bestDuration = sname, duration;
			end
		end
	end
	return best;
end

local function recent(count)
	local P, S = addon.Compat.PlainNumber, addon.Compat.PlainString;
	local sessions = C_DamageMeter.GetAvailableCombatSessions() or {};
	local parts = {};
	for i = math.max(1, #sessions - count + 1), #sessions do
		local s = sessions[i];
		local id, duration = P(s.sessionID), P(s.durationSeconds);
		parts[#parts + 1] = (id and tostring(id) or "?") .. " " .. (S(s.name) or "?") .. " "
			.. (duration and string.format("%.0f", duration) or "?") .. "s";
	end
	return #parts > 0 and table.concat(parts, ", ") or "none";
end

-- The meter's last `count` sessions as "id name duration", for the discover log (addon:Discover).
-- "?" stands for a value that is secret or missing, "unreadable" for a list that throws.
function SessionTotals.Recent(count)
	if not C_DamageMeter or not C_DamageMeter.GetAvailableCombatSessions then return "none" end
	local ok, text = pcall(recent, count);
	return ok and text or "unreadable";
end

-- { [spellID] = effective healing } for the player over the sessions from < id <= to, and what
-- session `from` gained since the read that ended on it. A read that succeeds is remembered, so
-- the same healing is handed out once.
-- nil without the API or while any value is secret (iterating a secret table throws: same answer).
function SessionTotals.Read(from, to)
	if not C_DamageMeter or not C_DamageMeter.GetCombatSessionSourceFromID then return nil end
	local ok, totals, last = pcall(read, from, to);
	if not ok or not totals then return nil end
	if last then taken = { id = to, totals = last } end
	return totals;
end

addon.SessionTotals = SessionTotals;
