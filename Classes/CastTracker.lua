local name, addon = ...;

--[[----------------------------------------------------------------------------
	CastTracker - counts chain casts (a cast started within 1/3 s of the previous
	one ending, or an instant used right as a cast lands). Feeds the haste HPCT
	estimate in Segment:GetHasteHPCT.
------------------------------------------------------------------------------]]
local CastTracker = {};
local endcast = 0;
local castedSpellID = 0;
local leniancy = 0.33333;

function CastTracker:IncChainCasts()
	local cur_seg = addon.SegmentManager:Get(0);
	local ttl_seg = addon.SegmentManager:Get("Total");
	if cur_seg then cur_seg:IncChainCasts() end
	if ttl_seg then ttl_seg:IncChainCasts() end
end

-- UNIT_SPELLCAST_START
function CastTracker:StartCast(unit)
	if not addon.inCombat then return end
	local _, _, _, startTimeMS, endTimeMS, _, _, _, spellID = UnitCastingInfo("player");
	if not addon.Spells:Get(spellID) then return end
	if addon.BuffTracker:CompareTimestamps(startTimeMS / 1000, endcast, leniancy) then
		castedSpellID = spellID;
	end
	endcast = endTimeMS / 1000;
end

-- UNIT_SPELLCAST_SUCCEEDED
local reported = {};

function CastTracker:FinishCast(unit, castGUID, spellID)
	if not addon.inCombat then return end
	local curTime = GetTime();
	if not addon.Spells:Get(spellID) then
		if HSW_ENABLE_FOR_TESTING and not reported[spellID] then
			addon:Msg("Spellcast Discovered: " .. tostring(spellID));
			reported[spellID] = true;
		end
		return;
	end

	if castedSpellID == spellID then
		self:IncChainCasts();            -- cast-time spell chained onto the previous cast
		endcast = curTime;
	else
		local start, dur = addon.Compat.GetSpellCooldown(spellID);
		if start and start > 0 then      -- instant with a cooldown, used right as a cast landed
			if addon.BuffTracker:CompareTimestamps(curTime, endcast, leniancy) then
				self:IncChainCasts();
			end
			endcast = start + dur;
		else
			endcast = curTime;
		end
	end
	castedSpellID = 0;
end

addon.CastTracker = CastTracker;
