local name, addon = ...;
addon.TimestampDelta = 0.050; -- 50ms

--[[----------------------------------------------------------------------------
	BuffTracker - stack counts of tracked player buffs, refreshed on UNIT_AURA
	instead of scanning auras on every healing event.
------------------------------------------------------------------------------]]
local BuffTracker = {};

function BuffTracker:Track(spellId, fApply, fExpires)
	self[spellId] = {
		expiration = 0,
		stacks = 0,
		onApply = fApply or nil,
		onExpires = fExpires or nil,
	};
end

-- True when two timestamps are within `leniancy` seconds (default 50ms).
function BuffTracker:CompareTimestamps(ts1, ts2, leniancy)
	ts1 = ts1 or 0;
	ts2 = ts2 or 0;
	leniancy = leniancy or addon.TimestampDelta;
	return ts1 > 0 and ts2 > 0 and math.abs(ts1 - ts2) <= leniancy;
end

function BuffTracker:UpdatePlayerBuffs()
	local found = {};
	for i = 1, 40 do
		local count, expiration, _, id, blocked = addon.Compat.UnitAura("player", i);
		if blocked then return end -- auras unreadable in combat: keep the last known state
		if not id then break end
		local t = self[id];
		if t then
			t.expiration = expiration or 0;
			found[id] = true;
			if not count or not tonumber(count) or count == 0 then count = 1 end
			local old = t.stacks;
			t.stacks = count;
			if count > old and t.onApply then t.onApply(count, old) end
			if count < old and t.onExpires then t.onExpires(count, old) end
		end
	end
	-- tracked buffs that fell off
	for id, t in pairs(self) do
		if type(t) == "table" and not found[id] and t.stacks ~= 0 then
			local old = t.stacks;
			t.stacks = 0;
			if t.onExpires then t.onExpires(0, old) end
		end
	end
end

function BuffTracker:Get(spellId)
	local t = self[spellId];
	if t and (t.expiration == 0 or GetTime() <= t.expiration) then
		return t.stacks;
	end
	return 0;
end

--[[----------------------------------------------------------------------------
	Forever closes the aura API in combat, so buffs the player casts are marked
	from UNIT_SPELLCAST_SUCCEEDED instead (UNIT_AURA still refreshes them out of
	combat). Debuffs we put on others (Weakened Soul) are kept by unit name.
------------------------------------------------------------------------------]]
function BuffTracker:MarkCast(spellId, duration)
	local t = self[spellId];
	if not t then return end
	local old = t.stacks;
	t.stacks = 1;
	t.expiration = GetTime() + duration;
	if old == 0 and t.onApply then t.onApply(1, 0) end
end

function BuffTracker:Consume(spellId)
	local t = self[spellId];
	if not t or t.stacks == 0 then return end
	local old = t.stacks;
	t.stacks = 0;
	t.expiration = 0;
	if t.onExpires then t.onExpires(0, old) end
end

local targetMarks = {}; -- unit name -> { [spellId] = expiration }

function BuffTracker:MarkTarget(unitName, spellId, duration)
	targetMarks[unitName] = targetMarks[unitName] or {};
	targetMarks[unitName][spellId] = GetTime() + duration;
end

function BuffTracker:TargetHas(unit, spellId)
	local unitName = UnitName(unit);
	local marks = unitName and targetMarks[unitName];
	local expiration = marks and marks[spellId];
	return (expiration ~= nil and GetTime() <= expiration) and true or false;
end

addon.BuffTracker = BuffTracker;
