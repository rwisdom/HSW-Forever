local name, addon = ...;

--[[----------------------------------------------------------------------------
	Forever constants
------------------------------------------------------------------------------]]
addon.CritBonus = 0.5;              -- heals crit for +50%
addon.ManaPerInt = 15;
addon.FSR_SECONDS = 5;              -- five-second rule

-- Intellect per 1% spell crit, keyed by level. 30: foreverdb.net/stats (beta); 60: foreverdb.net/stats
-- datamined from client build 1.60.1.70862 (2026-11-09). The value grows about one point per level,
-- so the lookup interpolates linearly between keyed levels and clamps outside them.
local IntPerCritByLevel = {
	PALADIN = { [10] = 16.3, [30] = 31.9, [60] = 59.9 }, -- 10: measured in game 2026-10-23 (51 Int -> +3.13% crit after 13 rating)
	PRIEST  = { [30] = 26.9, [60] = 59.5 },
	SHAMAN  = { [26] = 24.4, [28] = 26.3, [30] = 28.2, [60] = 59.2 }, -- measured in game: 26 on 2026-11-12 (53 Int -> +2.168% crit), 28 on 2026-10-22 (33 Int -> +1.254% crit)
	DRUID   = { [30] = 28.4, [60] = 59.9 },
};

local function lookupIntPerCrit(class, level)
	local byLevel = IntPerCritByLevel[class];
	if not byLevel then return 1 end -- unsupported class: never used
	local lo, hi; -- nearest keyed levels at or below / at or above the player's
	for lvl in pairs(byLevel) do
		if lvl <= level and (not lo or lvl > lo) then lo = lvl end
		if lvl >= level and (not hi or lvl < hi) then hi = lvl end
	end
	if not lo then return byLevel[hi] end
	if not hi or hi == lo then return byLevel[lo] end
	return byLevel[lo] + (byLevel[hi] - byLevel[lo]) * (level - lo) / (hi - lo);
end

--[[----------------------------------------------------------------------------
	Spirit regen. Measured on Forever with gear MP5 taken out (level-10 paladin, level-28 shaman,
	2026-10-22/23): base regen = min(Spirit / 4, 6.25 + Spirit / 8) mana per second, so a point
	of Spirit is worth 0.25 mana/s under 50 Spirit and 0.125 from 50 up.
------------------------------------------------------------------------------]]
addon.RegenKnee = 50;

-- Mana per second Spirit alone regenerates outside the five-second rule.
function addon:SpiritRegen(spirit)
	return math.min(spirit / 4, 6.25 + spirit / 8);
end

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
	if self.equipmentDirty and not self.inCombat then self:UpdateEquipment() end -- a swap made in combat
	-- per-second rates. Both hold, in full, whatever is flat: gear MP5 (verified 2026-10-22), a
	-- drink while seated and a buff the client counts (Might of Stormwind's 10 MP5; seen 2026-11-11).
	-- Spirit alone gives SpiritRegen, so what the base rate holds above it is that flat part (never
	-- less than the gear MP5 read from the items). Taken out of both, what is left is Spirit regen
	-- and its casting share, which includes regen talents and Innervate. The flat part is not
	-- taken from the drink's text: the rates pick a drink up and let it go on their own time
	-- (a pull while seated left 64.93 / 57.36 behind for 15.13 / 7.56, 2026-11-13). Blessing of
	-- Wisdom is not in the rates at all.
	local base, casting = GetManaRegen();
	local gear = (self.ply_mp5 or 0) / 5;
	base, casting = P(base), P(casting);
	self.ply_flat = base and math.max(gear, base - self:SpiritRegen(self.ply_spi)) or self.ply_flat or gear;
	self.ply_regen_base = base and math.max(base - self.ply_flat, 0) or self.ply_regen_base or 0;
	self.ply_regen_cast = casting and math.max(casting - self.ply_flat, 0) or self.ply_regen_cast or 0;
	self.ply_castpct = self.ply_regen_base > 0 and math.min(self.ply_regen_cast / self.ply_regen_base, 1) or 0;
	self.ManaDeficit:OnRates();
	local intmult = 1;
	for talent, perRank in pairs(IntTalents) do
		intmult = intmult + perRank * self:GetTalentRank(talent);
	end
	self.ply_intmult = intmult;
	-- The Human Spirit is 10% since the racial pass of 26 Oct 2026 (was 5%).
	self.ply_spiritmult = 1 + 0.05 * self:GetTalentRank("Living Spirit") + (UnitRace("player") == "Human" and 0.10 or 0);
	self.RegenPerSpirit = self:GetRegenPerSpirit();
end

-- Gear MP5 and set pieces, read on PLAYER_EQUIPMENT_CHANGED rather than on every aura change. Item
-- data may be secret in combat (a weapon swap can happen there): the read waits for combat to end.
function addon:UpdateEquipment()
	if self.inCombat then self.equipmentDirty = true; return end
	self.equipmentDirty = nil;
	local _, class = UnitClass("player");
	self.ply_mp5 = self:EquippedMP5();
	if class == "SHAMAN" then self.ply_earthfury = self:EquippedPieces(self.Shaman.Earthfury.pieces) end
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
	Per-heal derivatives, in healing per 1 stat point (crit: per 1% of crit chance, the unit item
	tooltips use; 1% is 14 rating underneath, checklist A23). `heal` is the non-crit amount.
	The results are real healing, crits included, the unit of the mana terms (Segment:GetFillerHPM):
	Allocate scales +Healing and haste by the crits that come on top of `heal`.
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

-- value of +1% crit chance: one hit in a hundred more gains the crit bonus
local function critPer1Pct(s, heal, CB)
	if not s.canCrit then return 0 end
	return heal * CB / 100;
end

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
--   CritBonus(ev, s, destUnit, CB) -> CB            per-spell crit healing bonus (Holy Power)
--   FlatBonus(ev, s, destUnit) -> amount            fixed part of one heal that +Healing did not produce (Oath of Light)
--   CriticalStrike(ev, s, heal, destUnit, C, CB, seg) -> extra crit value of one hit of `heal` (mana returned on crit)
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

--[[----------------------------------------------------------------------------
	Event log - one CSV row per cast and per attributed heal on the live segment,
	the inputs the weights are built from. Columns: addon.EventsHeader.
------------------------------------------------------------------------------]]
addon.EventsHeader = "time,event,spell_id,spell,target,amount,crit,mana";

function addon:LogEvent(kind, s, target, amount, crit, cost)
	if not self.hsw.db.global.logEvents then return end
	local seg = self.SegmentManager:Get(0);
	if not seg or seg.startTime < 0 then return end
	table.insert(seg.events, string.format("%.2f,%s,%d,%s,%s,%s,%s,%s",
		GetTime() - seg.startTime, kind, s.spellID, s.name, target or "",
		amount and string.format("%g", amount) or "",
		crit == nil and "" or (crit and "1" or "0"),
		cost and string.format("%g", cost) or ""));
end

--[[----------------------------------------------------------------------------
	Discover log - discover mode (/hsw discover on) narrates the fight boundaries and
	the heals it could not place. Each line goes to chat and, with the time, to the
	saved variables (HSW_DB.global.discoverLog), so a run is read from the file after
	a logout or /reload with no chat copy.
------------------------------------------------------------------------------]]
local DISCOVER_LOG_SIZE = 2000;

function addon:Discover(text)
	if not self.discoverSpells then return end
	self:Msg("[HealerStatWeights]: " .. text);
	local log = self.hsw.db.global.discoverLog;
	log[#log + 1] = date("%m-%d %H:%M:%S") .. " " .. text;
	if #log > DISCOVER_LOG_SIZE then table.remove(log, 1) end
end

function StatParser:IncManaRestore(mana)
	addon.SegmentManager:ForEachLive(function(seg) seg:IncManaRestore(mana) end);
	addon.ManaDeficit:Gain(mana, nil, "mana return");
end

local function liveSegments()
	local t = {};
	addon.SegmentManager:ForEachLive(function(seg) t[#t + 1] = seg end);
	return t;
end

local function critBonus(f, ev, s, destUnit)
	return f.CritBonus and f.CritBonus(ev, s, destUnit, addon.ply_crtbonus) or addon.ply_crtbonus;
end

--[[----------------------------------------------------------------------------
	Allocate - compute derivatives for `n` hits of a spell part that healed `heal` between them
	and add them to `segments`. heal is already crit-normalised.
------------------------------------------------------------------------------]]
function StatParser:Allocate(ev, s, heal, n, destUnit, f, SP, C, CB, H, segments)
	if HSW_ENABLE_FOR_TESTING then
		addon:Msg("allocate spellid=" .. tostring(s.spellID) .. " destunit=" .. tostring(destUnit) .. " amount=" .. heal);
	end

	if f.CritChance then C = f.CritChance(ev, s, destUnit, C) end
	-- real healing per point of non-crit healing: +Healing and haste raise the crits with the rest
	local crits = s.canCrit and 1 + math.min(C, 1) * CB or 1;
	-- a flat add-on (Oath of Light) crits with the rest of the heal but did not come from +Healing
	local flat = (f.FlatBonus and f.FlatBonus(ev, s, destUnit) or 0) * n;
	local _SP = _Healing(ev, s, math.max(heal - flat, 0), SP) * crits;
	local _C  = critPer1Pct(s, heal, CB);
	local _H  = _Haste(s, heal, H) * crits;
	-- 1 Int on gear is ply_intmult Int on the sheet, and sheet Int buys crit like gear crit does: with
	-- all a crit brings (returned mana, Divine Aegis), at IntPerCrit Int a percent.
	-- Verified in game 2026-11-12 on Ancestral Knowledge 5/5 (checklist A22): the talent multiplies
	-- gear Int, and sheet Int gives crit at one rate whatever raised it.
	local intmult = addon.ply_intmult or 1;

	for _, seg in ipairs(segments) do
		local c  = f.CriticalStrike and f.CriticalStrike(ev, s, heal / n, destUnit, C, CB, seg) * n or 0; -- per hit
		local i  = f.Intellect and f.Intellect(ev, s, heal, destUnit, _SP, seg) or 0;
		local sp = f.Spirit and f.Spirit(ev, s, heal, destUnit, _SP, seg) or 0;
		seg:AllocateHeal(_SP, _C + c, _H, ((_C + c) / addon.IntPerCrit + i) * intmult, sp, s.spellID);
	end

	addon:UpdateDisplayStats();
end

--[[----------------------------------------------------------------------------
	CreditHealing - add `total` effective healing of spell s to `segments`.
	PriceHealing - price `n` hits that healed `normalised` between them (the non-crit
	equivalent) through Allocate. Healing is credited before it is priced: the mana a crit
	returns is valued at the segment's healing per mana, which needs the whole fight in it.
------------------------------------------------------------------------------]]
function StatParser:CreditHealing(s, total, segments)
	-- a "% of base mana" spell has no table cost: it is a filler only while the client prices it,
	-- the same condition under which its cast recorded filler mana (Events.lua)
	local filler = s.filler and (s.manaCost > 0 or (addon.Compat.GetSpellManaCost(s.spellID) or 0) > 0);
	for _, seg in ipairs(segments) do
		if filler then seg:IncFillerHealing(total) end
		seg:IncTotalHealing(total);
	end
end

function StatParser:PriceHealing(ev, s, normalised, n, destUnit, f, segments)
	self:Allocate(ev, s, normalised, n, destUnit, f, addon.ply_sp, addon.ply_crt, critBonus(f, ev, s, destUnit), addon.ply_hst, segments);
end

--[[----------------------------------------------------------------------------
	DecompHealingForCurrentSpec - entry point from HealMatcher for every heal it
	attributes. The amount is secret on the release client, so the heal is counted on
	the live segments and priced from the session totals when the fight ends.
------------------------------------------------------------------------------]]
function StatParser:DecompHealingForCurrentSpec(ev, destGUID, spellID, critFlag)
	local f, specId = self:GetParserForCurrentSpec();
	if not f then return end

	local s = addon.Spells:Get(spellID);
	if not s then
		addon:DiscoverIgnoredSpell(spellID);
		return;
	end
	if not addon.Spells:IsForSpec(s, specId) then return end

	local destUnit = addon.UnitManager:Find(destGUID); -- the player, the group and its pets only
	if not destUnit then return end

	if addon.hsw.db.global.excludeRaidHealingCooldowns and s.cd then return end
	local crit = critFlag and true or false;
	local tick = ev == "SPELL_PERIODIC_HEAL";
	local targetName = addon.Compat.PlainString(UnitName(destUnit));
	addon:LogEvent(tick and "tick" or "heal", s, targetName, nil, crit);
	if HSW_ENABLE_FOR_TESTING then
		addon:Msg("count spellid=" .. tostring(s.spellID) .. " destunit=" .. tostring(destUnit) .. " tick=" .. (tick and 1 or 0) .. " crit=" .. (crit and 1 or 0));
	end
	-- no energize events on Forever: mana returned by this crit is credited analytically, now,
	-- while the buff that decides it (Water Shield) is in the state it had at the crit
	if crit and f.ManaReturn then
		local mana = f.ManaReturn(ev, s, nil, destUnit);
		if mana and mana > 0 then self:IncManaRestore(mana) end
	end
	addon.SegmentManager:ForEachLive(function(seg) seg:CountHeal(s.spellID, ev, targetName, crit) end);
end

-- One "total" row per spell part at fight end; the time column is the segment duration.
local function logTotal(seg, s, amount)
	if not addon.hsw.db.global.logEvents then return end
	table.insert(seg.events, string.format("%.2f,total,%d,%s,,%g,,", seg:GetDuration(), s.spellID, s.name, amount));
end

--[[----------------------------------------------------------------------------
	ApplyTotals - price a finished segment from the player's per-spell effective
	healing (SessionTotals.Read) and the hits counted during the fight. With n hits
	and k crits a part's total is about h * (n + k * CB) for a non-crit heal h, so the
	crit-normalised total is T * n / (n + k * CB). A spell with direct and periodic
	parts splits T by (n + k * CB) * expected size. Credits this segment, the Total and
	the fight's class total: all the healing first, then the pricing.
------------------------------------------------------------------------------]]
function StatParser:ApplyTotals(seg, totals)
	local f, specId = self:GetParserForCurrentSpec();
	if not f then return end
	local segments = { seg, addon.SegmentManager:Get("Total"), addon.SegmentManager:ClassTotal(seg) }; -- a nil class total ends the list
	local sp = addon.ply_sp or 0;
	local excludeCd = addon.hsw.db.global.excludeRaidHealingCooldowns;
	local parts = {}; -- { ev, s, normalised, hits, destUnit } per spell part, priced once every total is credited

	for spellID, T in pairs(totals) do
		local s = addon.Spells:Get(spellID);
		if not s then
			addon:DiscoverIgnoredSpell(spellID);
		elseif T > 0 and addon.Spells:IsForSpec(s, specId) and not (excludeCd and s.cd) then
			local h = seg.hits[s.spellID];
			local top = seg:TopTarget(s.spellID);
			local destUnit = top and addon.UnitManager:FindByName(top) or "player";
			local CB = critBonus(f, "SPELL_HEAL", s, destUnit);
			local d = h and h.direct or { n = 0, crit = 0 };
			local t = h and h.tick or { n = 0, crit = 0 };
			local wd = (d.n + d.crit * CB) * (s.base + s.coeff * sp);
			local wt = (t.n + t.crit * CB) * (s.baseTick + s.coeffTick * sp);
			local Td, Tt = 0, 0;
			if wd > 0 and wt > 0 then
				Td = T * wd / (wd + wt); Tt = T - Td;
			elseif wd > 0 then
				Td = T;
			elseif wt > 0 then
				Tt = T;
			else -- healing the matcher never saw: one non-crit heal of the part the spell has
				if s.coeff > 0 or s.base > 0 or s.tick == 0 then Td, d = T, { n = 1, crit = 0 } else Tt, t = T, { n = 1, crit = 0 } end
				addon:Discover("healing by " .. s.name .. " had no matched heals.");
			end
			if Td > 0 then
				logTotal(seg, s, Td);
				self:CreditHealing(s, Td, segments);
				parts[#parts + 1] = { "SPELL_HEAL", s, Td * d.n / (d.n + d.crit * CB), d.n, destUnit };
			end
			if Tt > 0 then
				logTotal(seg, s, Tt);
				self:CreditHealing(s, Tt, segments);
				parts[#parts + 1] = { "SPELL_PERIODIC_HEAL", s, Tt * t.n / (t.n + t.crit * CB), t.n, destUnit };
			end
		end
	end
	for _, p in ipairs(parts) do
		self:PriceHealing(p[1], p[2], p[3], p[4], p[5], f, segments);
	end
end

-- Power Word: Shield: absorbs are not observable on Forever, so the shield is credited at cast
-- time with its expected size (base + coeff * +Healing) as direct, non-crit healing.
function StatParser:DecompShieldCast(destGUID, spellID)
	local f, specId = self:GetParserForCurrentSpec();
	local s = addon.Spells:Get(spellID);
	if not f or not s or not addon.Spells:IsForSpec(s, specId) then return end
	local destUnit = addon.UnitManager:Find(destGUID);
	if not destUnit then return end
	local expected = s.base + s.coeff * (addon.ply_sp or 0);
	addon:LogEvent("heal", s, addon.Compat.PlainString(UnitName(destUnit)), expected, false);
	local segments = liveSegments();
	self:CreditHealing(s, expected, segments);
	self:PriceHealing("SPELL_HEAL", s, expected, 1, destUnit, f, segments);
end

addon.StatParser = StatParser;
