local name, addon = ...;

--[[----------------------------------------------------------------------------
	SpellType - which spec a spell belongs to. Retail spec ids are kept so
	history/SpecInfo keep working. PRIEST marks spells shared by Holy and
	Discipline; SHARED is for consumables/trinkets usable by every spec.
------------------------------------------------------------------------------]]
local SpellType = {
	DRUID = 105,
	SHAMAN = 264,
	HPRIEST = 257,
	DPRIEST = 256,
	PALADIN = 65,
	PRIEST = 5,
	SHARED = 1,
	IGNORED = -1,
};
local classTypeOfSpec = { [SpellType.HPRIEST] = SpellType.PRIEST, [SpellType.DPRIEST] = SpellType.PRIEST };

--[[----------------------------------------------------------------------------
	Spells - spell database. Numeric keys are spell entries (see Define).
	Entries come from Parsers/Spells_Generated.lua (tools/gen_spells.py) and
	Parsers/Spells_Manual.lua.
------------------------------------------------------------------------------]]
local Spells = {};
local aliases = {}; -- combat-log spell id -> spellbook id

-- o: coeff, base         (+Healing coefficient and tooltip midpoint of the direct heal)
--    coeffTick, baseTick (same for one periodic tick)
--    cast                (seconds; -1 = channeled; absent/0 = instant)
--    mana | manaPct      (absolute mana, or fraction of base mana resolved at cast time)
--    cd                  (true = raid cooldown, excluded by the option and never a filler)
--    canCrit             (default true; false for absorbs and Lay on Hands)
function Spells:Define(id, spellType, spellName, o)
	o = o or {};
	local cast = o.cast or 0;
	local mana = o.mana or 0;
	local cd = o.cd == true;
	local s = {
		spellID = id,
		spellType = spellType,
		name = spellName,
		coeff = o.coeff or 0,
		base = o.base or 0,
		coeffTick = o.coeffTick or 0,
		baseTick = o.baseTick or 0,
		canCrit = o.canCrit ~= false,
		hstHPCT = cast ~= 0,
		cd = cd,
		manaCost = mana,
		manaCostPctBase = o.manaPct,
		filler = (mana > 0 or o.manaPct ~= nil) and not cd,
	};
	self[id] = s;
	return s;
end

-- Some heals log under a different id than the spellbook entry (Holy Shock heal, Penance bolts, ...).
function Spells:Alias(eventId, bookId)
	aliases[eventId] = bookId;
end

function Spells:Get(id)
	id = id and tonumber(id);
	if not id then return nil end
	return self[aliases[id] or id];
end

function Spells:IsForSpec(s, specId)
	return s.spellType == specId
		or s.spellType == SpellType.SHARED
		or s.spellType == classTypeOfSpec[specId];
end

--[[----------------------------------------------------------------------------
	DiscoverIgnoredSpell - unknown healing event: remember it so we only report once
------------------------------------------------------------------------------]]
function addon:DiscoverIgnoredSpell(spellID)
	Spells:Define(spellID, SpellType.IGNORED, "unknown");
	if HSW_ENABLE_FOR_TESTING or self.discoverSpells then
		local spellName = self.Compat.GetSpellInfo(spellID);
		self:Msg("[HealerStatWeights]: healing spell " .. tostring(spellID) .. " (" .. tostring(spellName) .. ") is not in the database.");
	end
end

addon.Spells = Spells;
addon.SpellType = SpellType;
