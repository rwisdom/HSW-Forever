local name, addon = ...;

--[[----------------------------------------------------------------------------
	Compat - wrappers over APIs that moved into C_* namespaces on newer clients.
	Each prefers the namespaced form when present and falls back to the legacy global.
------------------------------------------------------------------------------]]
local Compat = {};

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
		if cd then return cd.startTime, cd.duration end
		return 0, 0;
	end
	return GetSpellCooldown(spellID);
end

-- Mana cost of a spell as the client reports it now (talent reductions included).
-- Returns nil when no cost API exists, 0 when the spell costs no mana.
function Compat.GetSpellManaCost(spellID)
	local f = (C_Spell and C_Spell.GetSpellPowerCost) or GetSpellPowerCost;
	if not f then return nil end
	local costs = f(spellID);
	if type(costs) ~= "table" then return nil end
	for _, c in ipairs(costs) do
		if c.type == 0 then return c.cost or 0 end -- Enum.PowerType.Mana == 0
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
function Compat.UnitAura(unit, i, filter)
	if C_UnitAuras and C_UnitAuras.GetAuraDataByIndex then
		local a = C_UnitAuras.GetAuraDataByIndex(unit, i, filter);
		if not a then return nil end
		return a.applications, a.expirationTime, a.sourceUnit, a.spellId;
	end
	local _, _, count, _, _, expiration, source, _, _, spellId = UnitAura(unit, i, filter);
	if not spellId then return nil end
	return count, expiration, source, spellId;
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
