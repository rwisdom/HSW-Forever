local name, addon = ...;

--[[----------------------------------------------------------------------------
	Forever constants
------------------------------------------------------------------------------]]
addon.CritBonus = 0.5;              -- heals crit for +50%
addon.CritRatingPerPct = 14;        -- 14 crit rating = 1% crit at every level
addon.ManaPerInt = 15;
addon.FSR_SECONDS = 5;              -- five-second rule

-- Intellect per 1% spell crit (foreverdb.net/stats, level 30). Keyed by level so
-- level-60 values can be added later; lookup uses the nearest keyed level <= player level.
local IntPerCritByLevel = {
	PALADIN = { [10] = 16.3, [30] = 31.9 }, -- 10: measured in game 2026-10-23 (51 Int -> +3.13% crit after 13 rating)
	PRIEST  = { [30] = 26.9 },
	SHAMAN  = { [28] = 26.3, [30] = 28.2 }, -- 28: measured in game 2026-10-22 (33 Int -> +1.254% crit)
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
	Spirit regen. Measured on Forever with gear MP5 taken out (level-10 paladin, level-28 shaman,
	2026-10-22/23): base regen = min(Spirit / 4, 6.25 + Spirit / 8) mana per second, so a point
	of Spirit is worth 0.25 mana/s under 50 Spirit and 0.125 from 50 up.
------------------------------------------------------------------------------]]
addon.RegenKnee = 50;

-- Mana per second one more point of Spirit gives at `spirit` (the player's effective Spirit by default).
function addon:GetRegenPerSpirit(spirit)
	return (spirit or self.ply_spi or 0) < self.RegenKnee and 0.25 or 0.125;
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
	["Mental Strength"]     = 0.02,
	["Heart of the Wild"]   = 0.02,
	["Ancestral Knowledge"] = 0.02,
};

function addon:UpdatePlayerStats()
	local _, class = UnitClass("player");
	-- In combat the client hides +Healing and crit (at least) behind secret values: keep the last
	-- readable value then. Gear cannot change in combat, so only procs are missed.
	local P = self.Compat.PlainNumber;
	self.ply_sp = P(GetSpellBonusHealing()) or self.ply_sp or 0;
	local crit = P(GetSpellCritChance(CritSchool[class] or 2));
	self.ply_crt = crit and crit / 100 or self.ply_crt or 0;
	self.ply_crtbonus = self.CritBonus;
	local hst = P(self.Compat.GetSpellHaste());
	self.ply_hst = hst and hst / 100 or self.ply_hst or 0;
	self.ply_int = P(select(2, UnitStat("player", 4))) or self.ply_int or 0;   -- effective (buffed) Intellect
	self.ply_spi = P(select(2, UnitStat("player", 5))) or self.ply_spi or 0;
	self.ply_maxmana = P(UnitPowerMax("player", 0)) or self.ply_maxmana or 0;
	if not self.inCombat then -- item data may be secret in combat; gear cannot change there
		self.ply_mp5 = self:EquippedMP5();
		if class == "SHAMAN" then self.ply_earthfury = self:EquippedPieces(self.Shaman.Earthfury.pieces) end
	end
	-- per-second rates; the ratio includes regen talents and Innervate. Gear MP5 sits in full in both
	-- (verified 2026-10-22): taken out, what is left is Spirit regen. Buff MP5 (Mana Spring, Wisdom) is not.
	local base, casting = GetManaRegen();
	local gear = (self.ply_mp5 or 0) / 5;
	base, casting = P(base), P(casting);
	self.ply_regen_base = base and math.max(base - gear, 0) or self.ply_regen_base or 0;
	self.ply_regen_cast = casting and math.max(casting - gear, 0) or self.ply_regen_cast or 0;
	self.ply_castpct = self.ply_regen_base > 0 and math.min(self.ply_regen_cast / self.ply_regen_base, 1) or 0;
	local intmult = 1;
	for talent, perRank in pairs(IntTalents) do
		intmult = intmult + perRank * self:GetTalentRank(talent);
	end
	self.ply_intmult = intmult;
	self.ply_spiritmult = 1 + 0.05 * self:GetTalentRank("Living Spirit") + (UnitRace("player") == "Human" and 0.05 or 0);
	self.RegenPerSpirit = self:GetRegenPerSpirit();
end

-- Mana per 5 s on the equipped items.
function addon:EquippedMP5()
	local n = 0;
	for slot = 1, 19 do
		local link = GetInventoryItemLink("player", slot);
		local stats = link and self.Compat.GetItemStats(link);
		n = n + (stats and self.Compat.PlainNumber(stats.ITEM_MOD_MANA_REGENERATION_SHORT) or 0);
	end
	return n;
end

-- How many of the named items the player wears.
function addon:EquippedPieces(names)
	local wanted, n = {}, 0;
	for _, iname in ipairs(names) do wanted[iname] = true end
	for slot = 1, 19 do
		local link = GetInventoryItemLink("player", slot);
		local iname = link and self.Compat.PlainString(self.Compat.GetItemInfo(link));
		if iname and wanted[iname] then n = n + 1 end
	end
	return n;
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
--   ManaReturn(ev, s, heal, destUnit) -> mana this crit returned (Illumination, Water Shield)
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

function StatParser:IncManaRestore(mana)
	local cur_seg, ttl_seg = segments();
	if cur_seg then cur_seg:IncManaRestore(mana) end
	if ttl_seg then ttl_seg:IncManaRestore(mana) end
end

--[[----------------------------------------------------------------------------
	Allocate - compute derivatives for one effective heal and add them to the
	current and Total segments. heal is already crit-normalised.
------------------------------------------------------------------------------]]
function StatParser:Allocate(ev, s, heal, destUnit, f, SP, C, CB, H)
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
function StatParser:DecompHealingForCurrentSpec(ev, destGUID, spellID, critFlag, heal)
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

	if addon.hsw.db.global.excludeRaidHealingCooldowns and s.cd then return end

	-- reduce crit heals to the non-crit amount
	local origHeal = heal;
	if critFlag then
		heal = heal / (1 + addon.ply_crtbonus);
	end

	self:IncHealing(origHeal, s.filler, true);
	-- no energize events on Forever: mana returned by this crit is credited analytically
	if critFlag and f.ManaReturn then
		local mana = f.ManaReturn(ev, s, origHeal, destUnit);
		if mana and mana > 0 then self:IncManaRestore(mana) end
	end
	self:Allocate(ev, s, heal, destUnit, f, addon.ply_sp, addon.ply_crt, addon.ply_crtbonus, addon.ply_hst);
end

-- Power Word: Shield: absorbs are not observable on Forever, so the shield is credited at cast
-- time with its expected size (base + coeff * +Healing) as direct, non-crit healing.
function StatParser:DecompShieldCast(destGUID, spellID)
	local s = addon.Spells:Get(spellID);
	if not s then return end
	self:DecompHealingForCurrentSpec("SPELL_HEAL", destGUID, spellID, false, s.base + s.coeff * (addon.ply_sp or 0));
end

addon.StatParser = StatParser;
