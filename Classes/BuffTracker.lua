local name, addon = ...;

--[[----------------------------------------------------------------------------
	BuffTracker - stack counts of tracked player buffs, refreshed on UNIT_AURA
	instead of scanning auras on every healing event.
------------------------------------------------------------------------------]]
local BuffTracker = {};

function BuffTracker:Track(spellId)
	self[spellId] = { expiration = 0, stacks = 0 };
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
			t.stacks = count;
		end
	end
	-- tracked buffs that fell off
	for id, t in pairs(self) do
		if type(t) == "table" and not found[id] then t.stacks = 0 end
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
	t.stacks = 1;
	t.expiration = GetTime() + duration;
end

function BuffTracker:Consume(spellId)
	local t = self[spellId];
	if not t then return end
	t.stacks = 0;
	t.expiration = 0;
end

local targetMarks = {}; -- unit name -> { [spellId] = expiration }

function BuffTracker:MarkTarget(unitName, spellId, duration)
	targetMarks[unitName] = targetMarks[unitName] or {};
	targetMarks[unitName][spellId] = GetTime() + duration;
end

-- Drops a mark from every unit (a buff the player may hold on one target at a time: Oath of Light).
function BuffTracker:UnmarkAll(spellId)
	for _, marks in pairs(targetMarks) do marks[spellId] = nil end
end

function BuffTracker:TargetHas(unit, spellId)
	local unitName = UnitName(unit);
	local marks = unitName and targetMarks[unitName];
	local expiration = marks and marks[spellId];
	return (expiration ~= nil and GetTime() <= expiration) and true or false;
end

addon.BuffTracker = BuffTracker;
