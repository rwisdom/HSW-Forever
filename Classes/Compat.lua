local name, addon = ...;

--[[----------------------------------------------------------------------------
	Compat - wrappers over APIs that moved into C_* namespaces on newer clients.
	Each prefers the namespaced form when present and falls back to the legacy global.
------------------------------------------------------------------------------]]
local Compat = {};

-- Forever's engine hands addons "secret" numbers for spell timing and similar values;
-- comparing or doing arithmetic on one throws. Returns v when it is a number the addon
-- may use, nil otherwise (callers fall back to "unknown").
function Compat.PlainNumber(v)
	if type(v) ~= "number" then return nil end
	if issecretvalue then
		if issecretvalue(v) then return nil end
		return v;
	end
	local ok = pcall(function() return v + 0 end);
	return ok and v or nil;
end

function Compat.GetSpellInfo(spellID)
	if C_Spell and C_Spell.GetSpellInfo then
		local info = C_Spell.GetSpellInfo(spellID);
		if info then return info.name, nil, info.iconID end
		return nil;
	end
	return GetSpellInfo(spellID);
end

function Compat.GetSpellCooldown(spellID)
	if C_Spell and C_Spell.GetSpellCooldown then
		local cd = C_Spell.GetSpellCooldown(spellID);
		if cd then return Compat.PlainNumber(cd.startTime), Compat.PlainNumber(cd.duration) end
		return 0, 0;
	end
	local start, duration = GetSpellCooldown(spellID);
	return Compat.PlainNumber(start), Compat.PlainNumber(duration);
end

-- Mana cost of a spell as the client reports it now (talent reductions included).
-- Returns nil when no cost API exists, 0 when the spell costs no mana.
function Compat.GetSpellManaCost(spellID)
	local f = (C_Spell and C_Spell.GetSpellPowerCost) or GetSpellPowerCost;
	if not f then return nil end
	local costs = f(spellID);
	if type(costs) ~= "table" then return nil end
	for _, c in ipairs(costs) do
		if c.type == 0 then return Compat.PlainNumber(c.cost or 0) end -- Enum.PowerType.Mana == 0; nil when secret
	end
	return 0;
end

function Compat.GetItemInfo(link)
	local f = (C_Item and C_Item.GetItemInfo) or GetItemInfo;
	if not f then return nil end
	return f(link);
end

function Compat.GetAddOnMetadata(addonName, field)
	local f = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata;
	if not f then return nil end
	return f(addonName, field);
end

-- Returns count, expirationTime, sourceUnit, spellId for the i-th aura, or nil when there is none.
-- In combat the client refuses aura reads outright ("Auras cannot be accessed when secret"): then
-- the 5th return is true so the caller can tell "unreadable" from "no more auras".
function Compat.UnitAura(unit, i, filter)
	if C_UnitAuras and C_UnitAuras.GetAuraDataByIndex then
		local ok, a = pcall(C_UnitAuras.GetAuraDataByIndex, unit, i, filter);
		if not ok then return nil, nil, nil, nil, true end
		if not a then return nil end
		return Compat.PlainNumber(a.applications), Compat.PlainNumber(a.expirationTime), a.sourceUnit, a.spellId;
	end
	local ok, _, _, count, _, _, expiration, source, _, _, spellId = pcall(UnitAura, unit, i, filter);
	if not ok then return nil, nil, nil, nil, true end
	if not spellId then return nil end
	return Compat.PlainNumber(count), Compat.PlainNumber(expiration), source, spellId;
end

function Compat.GetSpellHaste()
	if UnitSpellHaste then return UnitSpellHaste("player") or 0 end
	if GetHaste then return GetHaste() or 0 end
	return 0;
end

function Compat.OpenOptionsCategory(frame)
	if Settings and Settings.OpenToCategory and frame and frame.settingsCategoryID then
		Settings.OpenToCategory(frame.settingsCategoryID);
	elseif InterfaceOptionsFrame_OpenToCategory then
		InterfaceOptionsFrame_OpenToCategory(frame);
		InterfaceOptionsFrame_OpenToCategory(frame); -- twice: Blizzard bug on first open
	end
end

-- items: { {text=, isTitle=true} , {text=, func=, checked=} ... }
function Compat.ShowContextMenu(items, ownerFrame)
	if MenuUtil and MenuUtil.CreateContextMenu then
		MenuUtil.CreateContextMenu(ownerFrame, function(_, root)
			for _, item in ipairs(items) do
				if item.isTitle then root:CreateTitle(item.text)
				elseif item.func then root:CreateButton(item.text, item.func) end
			end
		end);
	else
		EasyMenu(items, ownerFrame, "cursor", 0, 0, "MENU");
	end
end

addon.Compat = Compat;
