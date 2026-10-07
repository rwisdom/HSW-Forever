local name, addon = ...;

--[[----------------------------------------------------------------------------
	Forever constants
------------------------------------------------------------------------------]]
addon.CritBonus = 0.5;              -- heals crit for +50%
addon.CritRatingPerPct = 14;        -- 14 crit rating = 1% crit at every level
addon.ManaPerInt = 15;
addon.FSR_SECONDS = 5;              -- five-second rule
addon.DefaultRegenPerSpirit = 0.1;  -- mana per second per Spirit until calibrated

-- Intellect per 1% spell crit (foreverdb.net/stats, level 30). Keyed by level so
-- level-60 values can be added later; lookup uses the nearest keyed level <= player level.
local IntPerCritByLevel = {
	PALADIN = { [30] = 31.9 },
	PRIEST  = { [30] = 26.9 },
	SHAMAN  = { [30] = 28.2 },
	DRUID   = { [30] = 28.4 },
};

local function lookupIntPerCrit(class, level)
	local byLevel = IntPerCritByLevel[class];
	if not byLevel then return 1 end -- unsupported class: never used
	local best, lowest;
	for lvl in pairs(byLevel) do
		if lvl <= level and (not best or lvl > best) then best = lvl end
		if not lowest or lvl < lowest then lowest = lvl end
	end
	return byLevel[best or lowest];
end

--[[----------------------------------------------------------------------------
	Spirit regen calibration
	db.regenCal["CLASS:level"] = { spirit1, regen1, spirit2, regen2 }
	Slope of base regen vs Spirit once two samples >= 20 Spirit apart exist.
	Known limitation: a gear swap that changes MP5 together with Spirit skews it.
------------------------------------------------------------------------------]]
local function regenCalKey()
	local _, class = UnitClass("player");
	return class .. ":" .. tostring(UnitLevel("player"));
end

function addon:GetRegenPerSpirit()
	local cals = self.hsw.db.global.regenCal;
	local cal = cals and cals[regenCalKey()];
	if cal and cal[3] and math.abs(cal[3] - cal[1]) >= 20 then
		local slope = (cal[4] - cal[2]) / (cal[3] - cal[1]);
		if slope > 0 then return slope end
	end
	return self.DefaultRegenPerSpirit;
end

function addon:SampleRegen(spirit, baseRegen)
	local db = self.hsw.db.global;
	db.regenCal = db.regenCal or {};
	local key = regenCalKey();
	local cal = db.regenCal[key];
	if not cal then
		db.regenCal[key] = { spirit, baseRegen };
	elseif math.abs(spirit - cal[1]) >= 20 then
		cal[3], cal[4] = spirit, baseRegen;
	else
		cal[1], cal[2] = spirit, baseRegen; -- refresh the anchor sample
	end
end

--[[----------------------------------------------------------------------------
	SetupConversionFactors - rating/stat conversions (level independent on Forever)
------------------------------------------------------------------------------]]
function addon:SetupConversionFactors()
	local db = self.hsw.db.global;
	local _, class = UnitClass("player");
	local level = math.max(UnitLevel("player") or 1, 1);
	self.CritConv = self.CritRatingPerPct;                 -- per-1% values / CritConv = per rating point
	self.HasteConv = 100 * (db.hasteRatingPerPct or 1);    -- heal/(1+H)/HasteConv = per haste point
	local override = db.intPerCritOverride and db.intPerCritOverride[class];
	if override and override > 0 then
		self.IntPerCrit = override;
	else
		self.IntPerCrit = lookupIntPerCrit(class, level);
	end
	self.RegenPerSpirit = self:GetRegenPerSpirit();
end

--[[----------------------------------------------------------------------------
	UpdatePlayerStats - read the character sheet
------------------------------------------------------------------------------]]
local CritSchool = { PALADIN = 2, PRIEST = 2, DRUID = 4, SHAMAN = 4 }; -- Holy / Nature
local IntTalents = {
	["Divine Intellect"]    = 0.02,
	["Mental Strength"]     = 0.03,
	["Heart of the Wild"]   = 0.02,
	["Ancestral Knowledge"] = 0.02,
};

function addon:UpdatePlayerStats()
	local _, class = UnitClass("player");
	self.ply_sp = GetSpellBonusHealing() or 0;
	self.ply_crt = (GetSpellCritChance(CritSchool[class] or 2) or 0) / 100;
	self.ply_crtbonus = self.CritBonus;
	self.ply_hst = (self.Compat.GetSpellHaste() or 0) / 100;
	self.ply_int = select(2, UnitStat("player", 4)) or 0;   -- effective (buffed) Intellect
	self.ply_spi = select(2, UnitStat("player", 5)) or 0;
	self.ply_maxmana = UnitPowerMax("player", 0) or 0;
	local base, casting = GetManaRegen();                    -- per-second rates; ratio includes regen talents and Innervate
	self.ply_regen_base = base or 0;
	self.ply_regen_cast = casting or 0;
	self.ply_castpct = self.ply_regen_base > 0 and math.min(self.ply_regen_cast / self.ply_regen_base, 1) or 0;
	local intmult = 1;
	for talent, perRank in pairs(IntTalents) do
		intmult = intmult + perRank * self:GetTalentRank(talent);
	end
	self.ply_intmult = intmult;
	self.ply_spiritmult = 1 + 0.05 * self:GetTalentRank("Living Spirit") + (UnitRace("player") == "Human" and 0.05 or 0);
	self:SampleRegen(self.ply_spi, self.ply_regen_base);
end

--[[----------------------------------------------------------------------------
	Per-heal derivatives, in healing per 1 stat point. `heal` is the non-crit amount.
------------------------------------------------------------------------------]]
-- +Healing: r = heal / (base + coeff*SP) absorbs every % multiplier; d(heal)/d(SP) = coeff * r
local function _Healing(ev, s, heal, SP)
	local coeff, base = s.coeff, s.base;
	if ev == "SPELL_PERIODIC_HEAL" then coeff, base = s.coeffTick, s.baseTick end
	if coeff <= 0 then return 0 end
	local expected = base + coeff * SP;
	if expected <= 0 then return 0 end
	return coeff * heal / expected;
end

-- value of +1% crit chance on this heal
local function critPer1Pct(s, heal, C, CB)
	if not s.canCrit then return 0 end
	C = math.min(C, 1);
	return heal * CB / (1 + C * CB) / 100;
end

local function _CriticalStrike(s, heal, C, CB) return critPer1Pct(s, heal, C, CB) / addon.CritConv end
local function _Intellect(s, heal, C, CB) return critPer1Pct(s, heal, C, CB) / addon.IntPerCrit end
local function _Haste(s, heal, H)
	if not s.hstHPCT then return 0 end
	return heal / (1 + H) / addon.HasteConv;
end

--[[----------------------------------------------------------------------------
	StatParser - per-spec parsers and the decomposition entry points
------------------------------------------------------------------------------]]
local StatParser = {};

-- overrides (all optional):
--   CritChance(ev, s, destUnit, C) -> C             per-spell crit chance (talents, buffs)
--   CriticalStrike(ev, s, heal, destUnit, C, CB, seg) -> extra crit value (mana returned on crit)
--   Intellect(ev, s, heal, destUnit, _SP, seg) -> extra Int value (Int -> +Healing talents)
--   Spirit(ev, s, heal, destUnit, _SP, seg) -> extra Spirit value (Spirit -> +Healing talents)
--   HealEvent(ev, s, heal, overhealing, destUnit, f, origHeal) -> true to skip allocation
function StatParser:Create(specId, overrides)
	self[specId] = overrides or {};
end

function StatParser:GetParserForCurrentSpec()
	local specId = addon:GetSpecId();
	return specId and self[specId] or nil, specId;
end

function StatParser:IsCurrentSpecSupported()
	return self:GetParserForCurrentSpec() ~= nil;
end

local function segments()
	return addon.SegmentManager:Get(0), addon.SegmentManager:Get("Total");
end

function StatParser:IncFillerHealing(heal)
	local cur_seg, ttl_seg = segments();
	if cur_seg then cur_seg:IncFillerHealing(heal) end
	if ttl_seg then ttl_seg:IncFillerHealing(heal) end
end

function StatParser:IncHealing(heal, updateFiller, updateTotal)
	local cur_seg, ttl_seg = segments();
	if cur_seg then
		if updateFiller then cur_seg:IncFillerHealing(heal) end
		if updateTotal then cur_seg:IncTotalHealing(heal) end
	end
	if ttl_seg then
		if updateFiller then ttl_seg:IncFillerHealing(heal) end
		if updateTotal then ttl_seg:IncTotalHealing(heal) end
	end
end

--[[----------------------------------------------------------------------------
	Allocate - compute derivatives for one effective heal and add them to the
	current and Total segments. heal/overhealing are already crit-normalised.
------------------------------------------------------------------------------]]
function StatParser:Allocate(ev, s, heal, overhealing, destUnit, f, SP, C, CB, H)
	if overhealing > 0 then return end -- any overheal: the marginal value of every stat is 0

	if HSW_ENABLE_FOR_TESTING then
		addon:Msg("allocate spellid=" .. tostring(s.spellID) .. " destunit=" .. tostring(destUnit) .. " amount=" .. heal);
	end

	if f.CritChance then C = f.CritChance(ev, s, destUnit, C) end
	local _SP = _Healing(ev, s, heal, SP);
	local _C  = _CriticalStrike(s, heal, C, CB);
	local _H  = _Haste(s, heal, H);
	local _I  = _Intellect(s, heal, C, CB);

	local function allocate(seg)
		local c  = f.CriticalStrike and f.CriticalStrike(ev, s, heal, destUnit, C, CB, seg) or 0;
		local i  = f.Intellect and f.Intellect(ev, s, heal, destUnit, _SP, seg) or 0;
		local sp = f.Spirit and f.Spirit(ev, s, heal, destUnit, _SP, seg) or 0;
		seg:AllocateHeal(_SP, _C + c, _H, _I + i, sp, s.spellID);
	end
	local cur_seg, ttl_seg = segments();
	if cur_seg then allocate(cur_seg) end
	if ttl_seg then allocate(ttl_seg) end

	addon:UpdateDisplayStats();
end

--[[----------------------------------------------------------------------------
	DecompHealingForCurrentSpec - entry point from SPELL_HEAL / SPELL_PERIODIC_HEAL
------------------------------------------------------------------------------]]
function StatParser:DecompHealingForCurrentSpec(ev, destGUID, spellID, critFlag, heal, overhealing)
	local f, specId = self:GetParserForCurrentSpec();
	if not f then return end

	local s = addon.Spells:Get(spellID);
	if not s then
		addon:DiscoverIgnoredSpell(spellID);
		return;
	end
	if not addon.Spells:IsForSpec(s, specId) then return end

	local destUnit = addon.UnitManager:Find(destGUID); -- excludes pets/npcs
	if not destUnit then return end

	-- reduce crit heals to the non-crit amount
	overhealing = overhealing or 0;
	local origHeal = heal;
	if critFlag then
		heal = heal / (1 + addon.ply_crtbonus);
		overhealing = overhealing / (1 + addon.ply_crtbonus);
	end

	local skipAllocate = false;
	if f.HealEvent then
		skipAllocate = f.HealEvent(ev, s, heal, overhealing, destUnit, f, origHeal);
	end

	if addon.hsw.db.global.excludeRaidHealingCooldowns and s.cd then return end

	self:IncHealing(origHeal, s.filler, true);
	if not skipAllocate then
		self:Allocate(ev, s, heal, overhealing, destUnit, f, addon.ply_sp, addon.ply_crt, addon.ply_crtbonus, addon.ply_hst);
	end
end

-- Power Word: Shield absorbs (SPELL_ABSORBED) count as direct, non-crit healing.
function StatParser:DecompAbsorb(destGUID, spellID, amount)
	self:DecompHealingForCurrentSpec("SPELL_HEAL", destGUID, spellID, false, amount, 0);
end

addon.StatParser = StatParser;
