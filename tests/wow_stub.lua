-- Minimal WoW API stubs. Tests change behaviour by editing the STUB table before loading addon files.
STUB = {
	time = 0, guid = "Player-1", level = 30, class = "PALADIN", race = "Human",
	stats = { [4] = {100, 110, 10, 0}, [5] = {50, 60, 10, 0} }, -- base, effective, posBuff, negBuff
	sp = 200, critPct = { [2] = 10, [4] = 12 }, haste = 0, maxMana = 3000,
	regen = { base = 10, cast = 3 },
	talents = {},   -- { {name="Holy", talents={ {name="Illumination", rank=5, max=5}, ... }}, ... }
	auras = {},     -- { {id=14751, count=1, expiration=0, source="player"}, ... }  (index order)
	cooldowns = {}, -- [spellID] = {start=, duration=}
	spellCost = {}, -- [spellID] = mana cost; nil → GetSpellPowerCost returns nil
	instance = { name = "Nowhere", type = "none", difficultyId = 0 },
};

function GetTime() return STUB.time end
function UnitGUID(u) if u == "player" or u == "Player" then return STUB.guid end return nil end
function UnitLevel() return STUB.level end
function UnitClass() return STUB.class, STUB.class end
function UnitRace() return STUB.race end
function UnitStat(_, i) local t = STUB.stats[i] or {0, 0, 0, 0}; return t[1], t[2], t[3], t[4] end
function GetSpellBonusHealing() return STUB.sp end
function GetSpellCritChance(school) return STUB.critPct[school] or 0 end
function UnitSpellHaste() return STUB.haste end
function UnitPowerMax() return STUB.maxMana end
function GetManaRegen() return STUB.regen.base, STUB.regen.cast end
function GetNumTalentTabs() return #STUB.talents end
function GetTalentTabInfo(i)
	local tab = STUB.talents[i]; if not tab then return nil end
	local pts = 0; for _, t in ipairs(tab.talents) do pts = pts + (t.rank or 0) end
	return tab.name, "tabicon", pts
end
function GetNumTalents(i) return STUB.talents[i] and #STUB.talents[i].talents or 0 end
function GetTalentInfo(tab, i)
	local t = STUB.talents[tab] and STUB.talents[tab].talents[i]; if not t then return nil end
	return t.name, "icon_" .. t.name, 1, 1, t.rank or 0, t.max or 5
end
function UnitAura(_, i)
	local a = STUB.auras[i]; if not a then return nil end
	return "aura", "icon", a.count or 1, nil, nil, a.expiration or 0, a.source or "player", nil, nil, a.id
end
function UnitHealth() return 1000 end
function UnitHealthMax() return 1000 end
function GetSpellPowerCost(id) local c = STUB.spellCost[id]; if c == nil then return nil end; return { { type = 0, cost = c } } end
function GetSpellInfo(id) return "spell" .. tostring(id), nil, "icon" .. tostring(id) end
function GetSpellCooldown(id) local c = STUB.cooldowns[id]; if c then return c.start, c.duration end; return 0, 0 end
function GetInstanceInfo() return STUB.instance.name, STUB.instance.type, STUB.instance.difficultyId end
function IsInInstance() return STUB.instance.type ~= "none", STUB.instance.type end
function GetInventoryItemLink() return nil end
function GetItemInfo() return nil end
function UnitInRaid() return false end
function UnitInParty() return false end
function GetNumGroupMembers() return 0 end
function IsEquippedItem() return false end
function date() return "Jan 01, 12:00 AM" end
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function CreateFrame()
	local f = {};
	function f:RegisterUnitEvent() end
	function f:RegisterEvent() end
	function f:SetScript() end
	return f
end
-- Deliberately absent, as on Classic-family clients: MAX_TALENT_TIERS, NUM_TALENT_COLUMNS, C_ChallengeMode, GetSpecialization.

-- STUB.casting = { startMS=, endMS=, spellID= } while a cast is in progress
function UnitCastingInfo()
	local c = STUB.casting; if not c then return nil end
	return "spell", "", "icon", c.startMS, c.endMS, false, 1, false, c.spellID
end

HSW_TEST_ADDON = {
	hsw = {
		db = { global = { maxSegments = 10, excludeRaidHealingCooldowns = false, history = {}, front = 0, back = 0,
		                  historySize = 200, hasteRatingPerPct = 1, intPerCritOverride = {}, regenCal = {} } },
		RegisterEvent = function() end,
	},
};
function HSW_TEST_ADDON:Msg(s) end
function HSW_TEST_ADDON:UpdateDisplayStats() end
function HSW_TEST_ADDON:AdjustVisibility() end
function HSW_TEST_ADDON:SetupFrame() end
