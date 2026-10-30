local name, addon = ...;
local date = date;

--[[----------------------------------------------------------------------------
	Segment Class - Stores stat allocations for one fight (or the Total)

	segment.t holds per-heal derivatives in "healing per 1 stat point".
	Time/mana based values (MP5, Int mana pool, Spirit regen) are live getters
	built from the filler-spell healing-per-mana (HPM) and elapsed time, so they
	stay correct for the live panel, the Total segment and merged segments.
------------------------------------------------------------------------------]]
local Segment = {};

local function getStatTable()
	return { heal = 0, crit = 0, haste_hpct = 0, int = 0, spirit = 0 };
end

local copy = addon.Util.CopyTable;

function Segment.Create(id)
	local self = copy(Segment);
	self.t = getStatTable();
	self.id = id;
	self.nameSet = false;
	self.totalHealing = 0;
	self.fillerHealing = 0;
	self.fillerCasts = 0;
	self.fillerManaSpent = 0;   -- absolute mana
	self.manaRestore = 0;
	self.timeInFSR = 0;         -- seconds inside the five-second rule
	self.timeOutsideFSR = 0;
	self.castPctWeighted = 0;   -- sum of (casting regen / base regen) * dt
	self.totalDuration = 0;
	self.startTime = GetTime();
	self.fsrLastAccum = self.startTime;
	self.startTimeStamp = date("%b %d, %I:%M %p");
	self.chainHaste = 0;
	self.chainCasts = 0;
	self.debug = {};
	self.bossFight = false;
	return self;
end

--[[----------------------------------------------------------------------------
	Live getters
------------------------------------------------------------------------------]]
-- Healing per point of mana, from filler spells.
function Segment:GetFillerHPM()
	if self.fillerManaSpent <= 0 then return 0 end
	return self.fillerHealing / self.fillerManaSpent;
end

-- Healing attributable to 1 mp5 over this segment (continuous, FSR-independent).
function Segment:GetMP5()
	return self:GetDuration() / 5 * self:GetFillerHPM();
end

-- Healing attributable to the mana pool from 1 Intellect (spent once per fight).
function Segment:GetIntManaValue()
	return addon.ManaPerInt * (addon.ply_intmult or 1) * self:GetFillerHPM();
end

-- Healing attributable to the regen from 1 Spirit: full rate outside the FSR,
-- (casting/base) share inside it.
function Segment:GetSpiritRegenValue()
	local total = self.timeInFSR + self.timeOutsideFSR;
	if total <= 0 then return 0 end
	local castPctAvg = self.castPctWeighted / total;
	local effectiveSeconds = self.timeOutsideFSR + castPctAvg * self.timeInFSR;
	return (addon.RegenPerSpirit or 0) * (addon.ply_spiritmult or 1) * effectiveSeconds * self:GetFillerHPM();
end

-- Haste HPCT: chain-cast based estimate, capped by the per-heal upper bound.
function Segment:GetHasteHPCT()
	if self.chainCasts == 0 or self.fillerCasts == 0 then return 0 end
	local avgFillerHealingPerCast = self.fillerHealing / self.fillerCasts;
	local avgHasteDuringChainCasts = self.chainHaste / self.chainCasts;
	local est = avgFillerHealingPerCast * self.chainCasts / (1 + avgHasteDuringChainCasts) / addon.HasteConv;
	return math.min(est, self.t.haste_hpct);
end

--[[----------------------------------------------------------------------------
	Five-second-rule time accounting. Splits [fsrLastAccum, now] exactly into
	time inside the FSR (first FSR_SECONDS after addon.lastManaSpend) and outside.
------------------------------------------------------------------------------]]
function Segment:AccumulateFSR(now)
	if self.startTime < 0 then return end -- ended segment
	now = now or GetTime();
	local dt = now - self.fsrLastAccum;
	if dt <= 0 then return end
	local sinceSpend = self.fsrLastAccum - (addon.lastManaSpend or -math.huge);
	local inFSR = math.max(0, math.min(dt, addon.FSR_SECONDS - sinceSpend));
	self.timeInFSR = self.timeInFSR + inFSR;
	self.timeOutsideFSR = self.timeOutsideFSR + (dt - inFSR);
	self.castPctWeighted = self.castPctWeighted + (addon.ply_castpct or 0) * dt;
	self.fsrLastAccum = now;
end

--[[----------------------------------------------------------------------------
	AllocateHeal - add per-heal derivatives
------------------------------------------------------------------------------]]
function Segment:AllocateHeal(heal, crit, haste_hpct, int, spirit, spellId)
	self.t.heal       = self.t.heal + heal;
	self.t.crit       = self.t.crit + crit;
	self.t.haste_hpct = self.t.haste_hpct + haste_hpct;
	self.t.int        = self.t.int + int;
	self.t.spirit     = self.t.spirit + spirit;
	if HSW_ENABLE_FOR_TESTING and spellId then
		self.debug[spellId] = (self.debug[spellId] or 0) + heal;
	end
end

function Segment:GetDuration()
	local d = self.totalDuration;
	if self.startTime >= 0 then d = d + (GetTime() - self.startTime) end
	return d;
end

function Segment:End()
	self:AccumulateFSR(GetTime());
	self:SnapshotTalentsAndEquipment();
	self.totalDuration = self.totalDuration + (GetTime() - self.startTime);
	self.startTime = -1;
end

--[[----------------------------------------------------------------------------
	SnapshotTalentsAndEquipment
------------------------------------------------------------------------------]]
local function FetchItemInfoFromSlot(t, id)
	local link = GetInventoryItemLink("player", id);
	if link then
		local iname, _, _, ilvl, _, _, _, _, _, icon = addon.Compat.GetItemInfo(link);
		if ilvl and icon and iname then
			t[id] = { link = link, name = iname, ilvl = ilvl, icon = icon };
		end
	end
end

function Segment:SnapshotTalentsAndEquipment()
	self.talentsSnapshot = true;
	self.selectedTalents = addon.Util.GetTalentSnapshot();
	self.gear = self.gear or {};
	FetchItemInfoFromSlot(self.gear, 13);
	FetchItemInfoFromSlot(self.gear, 14);
end

--[[----------------------------------------------------------------------------
	Increment functions
------------------------------------------------------------------------------]]
function Segment:IncChainCasts()
	self.chainHaste = self.chainHaste + (addon.ply_hst or 0);
	self.chainCasts = self.chainCasts + 1;
end

function Segment:IncTotalHealing(amount) self.totalHealing = self.totalHealing + amount end
function Segment:IncFillerHealing(amount) self.fillerHealing = self.fillerHealing + amount end

function Segment:IncFillerCasts(manaCost)
	self.fillerCasts = self.fillerCasts + 1;
	self.fillerManaSpent = self.fillerManaSpent + manaCost;
end

-- Diagnostic only (/hsw debug): the crit value of returned mana is credited per heal by the parsers.
function Segment:IncManaRestore(amount) self.manaRestore = self.manaRestore + amount end

--[[----------------------------------------------------------------------------
	Debug - print internal values of this segment to chat
------------------------------------------------------------------------------]]
function Segment:Debug()
	print("StatTable (healing per 1 stat point)");
	for k, v in pairs(self.t) do print(string.format("t.%s = %.5f", k, v)) end
	print("Live getters");
	print(string.format("fillerHPM = %.5f  mp5 = %.5f  intMana = %.5f  spiritRegen = %.5f  hasteHPCT = %.5f",
		self:GetFillerHPM(), self:GetMP5(), self:GetIntManaValue(), self:GetSpiritRegenValue(), self:GetHasteHPCT()));
	print("Counters");
	for k, v in pairs(self) do
		if type(v) == "number" then print(string.format("%s = %.5f", k, v)) end
	end
	print(string.format("duration = %.5f", self:GetDuration()));
	print("Healing per spellID");
	for k, v in pairs(self.debug) do print(string.format("%s = %.5f", k, v)) end
end

addon.Segment = Segment;
