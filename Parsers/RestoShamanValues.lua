local name, addon = ...;

--[[----------------------------------------------------------------------------
	Resto Shaman: what each talent and relic was worth in a segment (Classes/TalentValues.lua).
	Every fn returns healing; rank is the points taken. Rough entries rest on an
	assumption, named beside them. Talents not listed heal nothing (threat, pushback,
	armor, Reincarnation, Nature's Swiftness, damage and melee talents).
	Mana cost reductions are taken to add up on the table cost, so one is worth the same
	whether or not another is in effect (to be checked in game).
------------------------------------------------------------------------------]]
local HealingWay = { 0.08, 0.17, 0.25 }; -- the tooltip's percent by rank

-- Table cost of the casts of every healing spell: the database's spells bar the totems.
local function healBaseMana(ctx)
	local n = 0;
	for spellName, r in pairs(ctx.seg.spells) do
		if not spellName:find("Totem$") then n = n + r.baseMana end
	end
	return n;
end

-- Healing from `share` of Spirit regen going on inside the five-second rule.
local function castingRegen(ctx, share)
	return share * (addon.ply_regen_base or 0) * ctx.seg.timeInFSR * ctx.hpm;
end

local function critPerPoint(ctx, rank) return rank * ctx.seg.t.crit end -- 1% crit on every heal per point

local talents = {
	["Tidal Mastery"]      = { fn = critPerPoint },
	["Thundering Strikes"] = { fn = critPerPoint },
	-- 15% of Intellect per point becomes +Healing, each point of it worth t.heal
	["Mental Quickness"] = { fn = function(ctx, rank) return 0.15 * rank * (addon.ply_int or 0) * ctx.seg.t.heal end },
	-- 2% per point of the Intellect before the talent, as sheet Intellect: a point of gear Intellect is ply_intmult of those
	["Ancestral Knowledge"] = { fn = function(ctx, rank)
		local mult = addon.ply_intmult or 1;
		return 0.02 * rank * (addon.ply_int or 0) / mult * (ctx.seg.t.int + ctx.seg:GetIntManaValue()) / mult;
	end },
	["Purification"] = { fn = function(ctx, rank) return ctx.seg.totalHealing * 0.02 * rank / (1 + 0.02 * rank) end },
	["Healing Way"] = { fn = function(ctx, rank)
		local bonus = HealingWay[rank] or 0.25;
		return ctx.spell("Healing Wave").healing * bonus / (1 + bonus);
	end },
	["Tidal Focus"]  = { fn = function(ctx, rank) return 0.01 * rank * healBaseMana(ctx) * ctx.hpm end },
	["Mindfulness"]  = { fn = function(ctx, rank) return castingRegen(ctx, 0.5 / 3 * rank) end },
	["Water Shield"] = { fn = function(ctx) return ctx.seg.manaRestore * ctx.hpm end },
	-- the Healing Stream part only: Mana Spring's mana cannot be seen
	["Restorative Totems"] = { fn = function(ctx, rank)
		return ctx.spell("Healing Stream Totem").healing * 0.1 * rank / (1 + 0.1 * rank);
	end },
	-- rough: a cast shorter by 0.1 s a point is worth what the same percent of haste is worth on Healing Wave
	["Improved Healing Wave"] = { rough = true, fn = function(ctx, rank)
		local hw, seg = ctx.spell("Healing Wave"), ctx.seg;
		if hw.casts == 0 or seg.fillerHealing <= 0 then return 0 end
		local cast = hw.castTime / hw.casts; -- table cast time, before the talent
		if cast <= 0.1 * rank then return 0 end
		return 100 * (cast / (cast - 0.1 * rank) - 1) * seg:GetHasteHPCT() * hw.healing / seg.fillerHealing;
	end },
	-- rough: its own healing less what its mana would have healed as a filler; the Chain Heal bonus on its target is not separable
	["Riptide"] = { rough = true, fn = function(ctx)
		local riptide = ctx.spell("Riptide");
		return math.max(0, riptide.healing - riptide.mana * ctx.hpm);
	end },
	-- rough: the shaman's own share of the totem's mana
	["Mana Tide Totem"] = { rough = true, fn = function(ctx) return ctx.seg.manaTideMana * ctx.hpm end },
	-- rough: 5% a point off every cast named "...Totem", from the mana paid with the talent in effect
	["Totemic Focus"] = { rough = true, fn = function(ctx, rank)
		return 0.05 * rank * ctx.seg.totemMana / (1 - 0.05 * rank) * ctx.hpm;
	end },
};

-- Item ids from the player, 2026-11-21. Each is priced as if worn; the formulas are linear in the
-- tallies, so they hold whether it was worn or not.
local relics = {
	{ name = "Tidal Totem", id = 272431, fn = function(ctx) return 0.05 * ctx.spell("Healing Wave").baseMana * ctx.hpm end },
	-- rough: one more globe is spent each time a heal crit empties the shield; globes hits on the shaman take in a fight are not seen
	{ name = "Totem of Sustaining", id = 23200, rough = true, fn = function(ctx)
		return ctx.seg.shieldsEmptied * addon.Shaman.WaterShieldReturn * (addon.ply_maxmana or 0) * ctx.hpm;
	end },
	{ name = "Totem of Urgency", id = 279249, fn = function(ctx) return 4 * ctx.spell("Lesser Healing Wave").crit end },
	{ name = "Totem of Tides", id = 22345, fn = function(ctx) return 0.05 * ctx.spell("Riptide").baseMana * ctx.hpm end },
	{ name = "Polished Driftwood Icon", id = 249398, fn = function(ctx) return castingRegen(ctx, 0.08) end },
};

addon.TalentValues:Register(addon.SpellType.SHAMAN, { talents = talents, relics = relics });
