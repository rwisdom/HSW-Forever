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

-- Raise the watermark to `id`, or to the newest readable session when none is given.
function SessionTotals.Advance(id)
	id = id or SessionTotals.Newest();
	if id and id > SessionTotals.watermark then SessionTotals.watermark = id end
end

local function read(from, to)
	local P = addon.Compat.PlainNumber;
	local totals = {};
	for id = from + 1, to do
		-- nil: no session with that id, or the player healed nothing in it
		local source = C_DamageMeter.GetCombatSessionSourceFromID(id, healingDone(), UnitGUID("player"));
		for _, spell in ipairs(source and source.combatSpells or {}) do
			local spellID, amount = P(spell.spellID), P(spell.totalAmount);
			if not spellID or not amount then return nil end
			totals[spellID] = (totals[spellID] or 0) + amount;
		end
	end
	return totals;
end

-- { [spellID] = effective healing } for the player over the sessions from < id <= to.
-- nil without the API or while any value is secret (iterating a secret table throws: same answer).
function SessionTotals.Read(from, to)
	if not C_DamageMeter or not C_DamageMeter.GetCombatSessionSourceFromID then return nil end
	local ok, totals = pcall(read, from, to);
	if not ok then return nil end
	return totals;
end

addon.SessionTotals = SessionTotals;
