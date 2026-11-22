local name, addon = ...;

--[[----------------------------------------------------------------------------
	TalentValues - what talents, relics and trinkets were worth in a segment, in
	points of +Healing: the healing they produced over the healing one point of
	+Healing produced (segment.t.heal), the scale on which the stat weights sit.

	A spec registers (Parsers/RestoShamanValues.lua):
	  talents = { [talentName] = { fn = function(ctx, rank) -> healing, rough = true|nil } }
	  relics  = { { name =, id =, fn = function(ctx) -> healing, rough = true|nil }, ... }  in display order
	fn returns the healing credited to the whole talent, or to the relic as if it had
	been worn. rough marks an estimate (drawn with "~"). A talent with no entry has no
	healing value.
	ctx: seg (the segment), hpm (its filler healing per mana), spell(name) (the
	segment's tallies of a spell, Segment:Spell).
------------------------------------------------------------------------------]]
local TalentValues = { specs = {} };

function TalentValues:Register(specId, def)
	self.specs[specId] = def;
end

local function context(seg)
	return { seg = seg, hpm = seg:GetFillerHPM(), spell = function(spellName) return seg:Spell(spellName) end };
end

-- Prices a talent snapshot ({ {name=, rank=, ...}, ... }) against the segment: each talent with a
-- formula gains value and rough. False when the spec has no formulas.
function TalentValues:PriceTalents(seg, specId, talents)
	local def = self.specs[specId];
	if not def or seg.t.heal <= 0 then return false end
	local ctx = context(seg);
	for _, talent in ipairs(talents) do
		local f = def.talents[talent.name];
		if f then
			talent.value = f.fn(ctx, talent.rank) / seg.t.heal;
			talent.rough = f.rough;
		end
	end
	return true;
end

-- The spec's relics, each priced as if worn: { { name=, icon=, value=, rough=, worn= }, ... }, nil
-- when the spec has none. worn is the gear snapshot of the relic slot (nil: empty or unreadable); a
-- worn relic that is not on the list gets a last row with no value. An icon comes from the client
-- by item id, which gives nothing for an item it has not loaded yet.
function TalentValues:PriceRelics(seg, specId, worn)
	local def = self.specs[specId];
	if not def or not def.relics or seg.t.heal <= 0 then return nil end
	local P, N = addon.Compat.PlainString, addon.Compat.PlainNumber;
	local ctx, rows, found = context(seg), {}, false;
	for _, relic in ipairs(def.relics) do
		local isWorn = worn ~= nil and worn.name == relic.name;
		found = found or isWorn;
		local _, _, _, _, _, _, _, _, _, icon = addon.Compat.GetItemInfo(relic.id);
		rows[#rows + 1] = {
			name = relic.name,
			icon = isWorn and worn.icon or N(icon) or P(icon),
			value = relic.fn(ctx) / seg.t.heal,
			rough = relic.rough,
			worn = isWorn or nil,
		};
	end
	if worn and not found then rows[#rows + 1] = { name = worn.name, icon = worn.icon, worn = true } end
	return rows;
end

-- Item stat key -> { the history entry's weight for it, how many of the stat make one unit of that weight }.
local TrinketStats = {
	ITEM_MOD_SPELL_HEALING_DONE_SHORT = { "Heal", 1 },  -- assumed: not yet seen on a Forever item (in-game checklist A25)
	ITEM_MOD_SPELL_POWER_SHORT        = { "Heal", 1 },  -- assumed
	ITEM_MOD_CRIT_RATING_SHORT        = { "Crt", 14 },  -- the weight is per 1% of crit, 14 rating (checklist A23)
	ITEM_MOD_INTELLECT_SHORT          = { "Int", 1 },
	ITEM_MOD_SPIRIT_SHORT             = { "Spi", 1 },   -- assumed
	ITEM_MOD_MANA_REGENERATION_SHORT  = { "Mp5", 1 },
};

-- What an item's plain stats (its GetItemStats table) are worth at the weights of history entry h;
-- nil when it has none of the priced stats. Use and proc effects are not priced, and haste is left
-- out until it has been seen on an item (checklist A8).
function TalentValues.Trinket(stats, h)
	local value;
	for key, w in pairs(TrinketStats) do
		local n = stats[key];
		if n then value = (value or 0) + n / w[2] * (h[w[1]] or 0) end
	end
	return value;
end

addon.TalentValues = TalentValues;
