local name, addon = ...;
local hsw = LibStub("AceAddon-3.0"):NewAddon("HealerStatWeights", "AceConsole-3.0", "AceEvent-3.0");
local lsmlists = AceGUIWidgetLSMlists;

local SCHEMA = 2; -- bump when history entries change shape; older entries are wiped on load

--[[----------------------------------------------------------------------------
	Defaults
------------------------------------------------------------------------------]]
local function Color(r, g, b, a)
	return { r = r, g = g, b = b, a = a or 1 };
end
local hswOptionsFrame;

local defaults = {
	global = {
		schema = 0,
		excludeRaidHealingCooldowns = false,
		fontSize = 12,
		frameWidth = 192,
		enabledInDungeons = true,
		enabledInRaids = true,
		enabledInBattlegrounds = false,
		frameLocked = false,
		maxSegments = 10,
		back = 0,
		front = 0,
		historySize = 200,
		alwaysShow = false,
		neverShow = false,
		alwaysEnabled = false,
		fontColor = Color(1, 1, 1, 1),
		fontStr = false,
		history = {},
		hasteRatingPerPct = 1,
		intPerCritOverride = { PALADIN = 0, PRIEST = 0, SHAMAN = 0, DRUID = 0 },
		regenCal = {},
	},
};

local historySelected = 0;

--[[----------------------------------------------------------------------------
	Labels
------------------------------------------------------------------------------]]
local SegmentLabels = {
	Heal     = "+Healing",
	HealPct  = "+Healing\nPer 1% HPS",
	Crt      = "Crit Rating",
	CrtPct   = "Crit Rating\nPer 1% HPS",
	Hst      = "Haste (HPCT)",
	HstPct   = "Haste (HPCT)\nPer 1% HPS",
	Int      = "Intellect",
	IntPct   = "Intellect\nPer 1% HPS",
	Spi      = "Spirit",
	SpiPct   = "Spirit\nPer 1% HPS",
	Mp5      = "MP5",
	Mp5Pct   = "MP5\nPer 1% HPS",
	Class    = "Class/Spec",
	Talents  = "Talents",
	Segment  = "Segment",
	Duration = "Duration",
	Name     = "Name",
	Region   = "Region",
	Realm    = "Realm",
	SpecID   = "SpecID",
	DateTime = "Date/Time",
	Slot13   = "Trinket 1",
	Slot14   = "Trinket 2",
};

local spec_labels = {
	[105] = "Restoration Druid",
	[264] = "Restoration Shaman",
	[257] = "Holy Priest",
	[65]  = "Holy Paladin",
	[256] = "Discipline Priest",
};

-- No GetSpecializationInfoByID on Classic-family clients: static icons.
local spec_icons = {
	[105] = "Interface\\Icons\\Spell_Nature_HealingTouch",
	[264] = "Interface\\Icons\\Spell_Nature_MagicImmunity",
	[257] = "Interface\\Icons\\Spell_Holy_GreaterHeal",
	[65]  = "Interface\\Icons\\Spell_Holy_HolyBolt",
	[256] = "Interface\\Icons\\Spell_Holy_WordFortitude",
};

-- Spec slot in Pawn's Classic class/spec list (verify on Forever, Task 17).
addon.PawnSpecIndex = { [65] = 1, [256] = 1, [257] = 2, [264] = 3, [105] = 3 };

local globalResources = {
	{
		key = "Do Stats Matter?",
		value = "A little. But, not as much as you might think. Seriously, simple gameplay improvements have a much larger impact on performance than your stats... and this is coming from someone who wrote an entire addon to calculate statweights for you. :)",
	},
	{
		key = "Forever\nData",
		value = "Spell coefficients and talents come from the talentsforever.com beta export. Forever is in beta: numbers can lag live tuning. Use /hsw discover on to report unknown healing spells.",
	},
};

--[[----------------------------------------------------------------------------
	Options
------------------------------------------------------------------------------]]
local options = {
	name = "Healer Stat Weights (Forever)",
	handler = hsw,
	childGroups = "tab",
	type = "group",
	args = {
		optionsTab = {
			name = "Options",
			type = "group",
			order = 1,
			args = {
				headerSettings = {
					name = "Calculation Settings",
					desc = "These settings control which calculations are performed.",
					type = "header",
					order = 1,
				},
				excludeBigCDs = {
					name = "Exclude Raid Healing Cooldowns",
					desc = "When checked, excludes Tranquility, Lay on Hands, Divine Grace and Desperate Prayer. Not retroactive: set it before combat.",
					type = "toggle",
					order = 2,
					width = "full",
					get = function(info) return hsw.db.global.excludeRaidHealingCooldowns end,
					set = function(info, val) hsw.db.global.excludeRaidHealingCooldowns = val end,
				},
				headerUI = {
					name = "UI Settings",
					desc = "These settings affect the UI of the addon.",
					type = "header",
					order = 8,
				},
				neverShowFrame = {
					name = "Never Show Stats Frame",
					type = "toggle",
					desc = "Hides the stats panel. Enabled content still gets logged to the history tab.",
					order = 9.1,
					width = "full",
					get = function(info) return hsw.db.global.neverShow end,
					set = function(info, val)
						if val then hsw.db.global.alwaysShow = false end
						hsw.db.global.neverShow = val;
						addon:AdjustVisibility();
					end,
				},
				showFrame = {
					name = "Always Show Stats Frame",
					type = "toggle",
					desc = "Always show the display panel, regardless of content. By default it only shows in enabled content.",
					order = 9.2,
					width = "full",
					disabled = function(info) return hsw.db.global.neverShow end,
					get = function(info) return hsw.db.global.alwaysShow end,
					set = function(info, val) hsw.db.global.alwaysShow = val; addon:AdjustVisibility(); end,
				},
				frameLocked = {
					name = "Lock Frame",
					desc = "Disable moving the stat weights frame by clicking & dragging.",
					type = "toggle",
					order = 10,
					width = "full",
					disabled = function(info) return hsw.db.global.neverShow end,
					get = function(info) return hsw.db.global.frameLocked end,
					set = function(info, val)
						hsw.db.global.frameLocked = val;
						if val then addon:Lock() else addon:Unlock() end
					end,
				},
				fontSize = {
					name = "Font Size",
					desc = "Adjust the font size of the stat weights frame.",
					type = "range",
					order = 11,
					min = 8, max = 18, step = 1,
					get = function(info) return hsw.db.global.fontSize end,
					set = function(info, val) hsw.db.global.fontSize = val; addon:AdjustFontSizes(); end,
				},
				frameWidth = {
					name = "Frame Width",
					desc = "Adjust the width of the stat weights frame.",
					type = "range",
					order = 12,
					min = 128, max = 256, step = 1,
					get = function(info) return hsw.db.global.frameWidth end,
					set = function(info, val) hsw.db.global.frameWidth = val; addon:AdjustWidth(val); end,
				},
				resetPosition = {
					name = "Reset Position",
					desc = "Reset the frame's position to the center of the screen.",
					type = "execute",
					order = 13,
					func = function() addon:ResetFramePosition() end,
				},
				fontStr = {
					type = "select",
					name = "Font Type",
					dialogControl = "LSM30_Font",
					order = 14,
					values = lsmlists.font,
					get = function(info) return hsw.db.global.fontStr end,
					set = function(info, val) hsw.db.global.fontStr = val; addon:AdjustFonts(); end,
				},
				fontColor = {
					name = "Font Color",
					type = "color",
					order = 15,
					get = function(info) local c = hsw.db.global.fontColor; return c.r, c.g, c.b, c.a end,
					set = function(info, r, g, b, a) hsw.db.global.fontColor = Color(r, g, b, a); addon:AdjustFontColor(); end,
				},
				headerContent = {
					name = "Content",
					desc = "Which content to calculate stat weights in.",
					type = "header",
					order = 20,
				},
				enabledAlways = {
					name = "Always Enabled",
					desc = "Run the addon in ANY content (open world, dummies). Instanced PvE gives the most useful numbers.",
					type = "toggle",
					order = 21,
					width = "full",
					get = function(info) return hsw.db.global.alwaysEnabled end,
					set = function(info, val) hsw.db.global.alwaysEnabled = val; addon:AdjustVisibility(); end,
				},
				enabledInDungeons = {
					name = "Dungeons",
					type = "toggle",
					order = 22,
					width = "full",
					disabled = function(info) return hsw.db.global.alwaysEnabled end,
					get = function(info) return hsw.db.global.enabledInDungeons end,
					set = function(info, val) hsw.db.global.enabledInDungeons = val; addon:AdjustVisibility(); end,
				},
				enabledInRaids = {
					name = "Raids",
					type = "toggle",
					order = 23,
					width = "full",
					disabled = function(info) return hsw.db.global.alwaysEnabled end,
					get = function(info) return hsw.db.global.enabledInRaids end,
					set = function(info, val) hsw.db.global.enabledInRaids = val; addon:AdjustVisibility(); end,
				},
				enabledInBattlegrounds = {
					name = "Battlegrounds",
					type = "toggle",
					order = 24,
					width = "full",
					disabled = function(info) return hsw.db.global.alwaysEnabled end,
					get = function(info) return hsw.db.global.enabledInBattlegrounds end,
					set = function(info, val) hsw.db.global.enabledInBattlegrounds = val; addon:AdjustVisibility(); end,
				},
				headerCalibration = {
					name = "Calibration",
					desc = "Conversion factors that Forever does not expose through the API.",
					type = "header",
					order = 30,
				},
				intPerCrit = {
					name = "Intellect per 1% spell crit for your class (0 = built-in table)",
					desc = "Built-in values are foreverdb.net level-30 numbers (Paladin 31.9, Priest 26.9, Shaman 28.2, Druid 28.4). Applies to new heals.",
					type = "input",
					order = 31,
					width = "full",
					get = function(info) local _, class = UnitClass("player"); return tostring(hsw.db.global.intPerCritOverride[class] or 0) end,
					set = function(info, val)
						local _, class = UnitClass("player");
						hsw.db.global.intPerCritOverride[class] = tonumber(val) or 0;
						addon:SetupConversionFactors();
						addon:UpdateDisplayStats();
					end,
				},
				hasteRatingPerPct = {
					name = "Haste rating per 1% haste (1 = report Haste per 1%)",
					desc = "Set this once the haste rating conversion is known. Applies to new heals.",
					type = "input",
					order = 32,
					width = "full",
					get = function(info) return tostring(hsw.db.global.hasteRatingPerPct or 1) end,
					set = function(info, val)
						local n = tonumber(val);
						if n and n > 0 then
							hsw.db.global.hasteRatingPerPct = n;
							addon:SetupConversionFactors();
							addon:UpdateDisplayStats();
						end
					end,
				},
			},
		},
		historyTab = {
			name = "History",
			desc = "Your most recent logged segments.",
			type = "group",
			order = 2,
			width = 2,
			args = {},
		},
	},
};

local BlizOptionsTable = {
	name = "Healer Stat Weights (Forever)",
	type = "group",
	args = {
		btn = {
			name = "/hsw",
			type = "execute",
			width = 1.0,
			func = function()
				hsw:OpenOptions();
				if InterfaceOptionsFrame_Show then InterfaceOptionsFrame_Show() end
			end,
		},
	},
};

--[[----------------------------------------------------------------------------
	History tab: one page per logged segment
------------------------------------------------------------------------------]]
function addon:BuildOptionsTableForHistorySegment(i)
	local h = self.History:Get(i);
	if not h then return nil end

	local OptionsBuilder = addon.OptionsBuilder.Create(h);

	local dateTimeStr = h.DateTime and ("|cFFCCCCCC" .. h.DateTime .. "|r ") or "";
	OptionsBuilder:AddText(dateTimeStr, 2.5);
	OptionsBuilder:AddHeaderButton("Pawn >>", "Export as Pawn String", function()
		historySelected = i;
		addon:CreatePawnStringFromHistory();
	end);
	OptionsBuilder:AddNewLine();

	local segmentName = h.Segment .. " (" .. h.Duration .. ")";
	local icon = spec_icons[h.SpecID];
	if icon then
		segmentName = "|T" .. icon .. ":24|t " .. segmentName;
	end
	OptionsBuilder:AddHeaderRow(segmentName);
	OptionsBuilder:AddNewLine();

	-- Talents: { {name=, icon=, rank=}, ... } from Segment:SnapshotTalentsAndEquipment
	local str = "";
	for _, talent in ipairs(h.Talents or {}) do
		if type(talent) == "table" and talent.icon then
			str = str .. "|T" .. tostring(talent.icon) .. ":24|t" .. tostring(talent.rank or "") .. " ";
		end
	end

	local function gearStr(gearTbl)
		if not gearTbl then return nil end
		local s = gearTbl.icon and ("|T" .. tostring(gearTbl.icon) .. ":16|t ") or "";
		return s .. (gearTbl.ilvl or "") .. " " .. (gearTbl.link or "");
	end

	OptionsBuilder:AddDivider("Gear & Talents");
	OptionsBuilder:AddNewLine();
	OptionsBuilder:AddHeaderRow(str);

	for _, slot in ipairs({ "Slot13", "Slot14" }) do
		local s = gearStr(h[slot]);
		if s then
			OptionsBuilder:AddNewLine();
			OptionsBuilder:AddHeaderRow(s);
			OptionsBuilder:AddNewLine();
		end
	end
	OptionsBuilder:AddNewLine();

	OptionsBuilder:AddDivider("Stat Weights");
	OptionsBuilder:AddKVPair("Heal");
	OptionsBuilder:AddKVPair("Crt");
	OptionsBuilder:AddNewLine();
	OptionsBuilder:AddNewLine();
	OptionsBuilder:AddKVPair("Hst");
	OptionsBuilder:AddKVPair("Int");
	OptionsBuilder:AddNewLine();
	OptionsBuilder:AddNewLine();
	OptionsBuilder:AddKVPair("Spi");
	OptionsBuilder:AddKVPair("Mp5");
	OptionsBuilder:AddNewLine();
	OptionsBuilder:AddNewLine();

	if h.HealPct and h.HealPct > 0 then
		local pctOptions = { Type = "integer" };
		OptionsBuilder:AddDivider("Stat Points Per 1% HPS");
		OptionsBuilder:AddKVPair("HealPct", pctOptions);
		OptionsBuilder:AddKVPair("CrtPct", pctOptions);
		OptionsBuilder:AddNewLine();
		OptionsBuilder:AddNewLine();
		OptionsBuilder:AddKVPair("HstPct", pctOptions);
		OptionsBuilder:AddKVPair("IntPct", pctOptions);
		OptionsBuilder:AddNewLine();
		OptionsBuilder:AddNewLine();
		OptionsBuilder:AddKVPair("SpiPct", pctOptions);
		OptionsBuilder:AddKVPair("Mp5Pct", pctOptions);
		OptionsBuilder:AddNewLine();
		OptionsBuilder:AddNewLine();
	end

	if self.SpecInfo[h.SpecID] then
		OptionsBuilder:AddDivider("Resources");
		local specInfoOptions = { Width = 2.75, Type = "string" };
		for _, list in ipairs({ globalResources, self.SpecInfo[h.SpecID] }) do
			for _, v in ipairs(list) do
				if v.key == "url" then
					OptionsBuilder:AddURL(v.value, v.name, v.desc);
				else
					OptionsBuilder:AddKVPairRaw(v.key, v.value, specInfoOptions);
				end
				OptionsBuilder:AddNewLine();
				OptionsBuilder:AddNewLine();
			end
		end
	end

	return OptionsBuilder:GetOptions();
end

local function TryBuildHistoryList()
	if not addon.History:GetDirty() then return false end
	local historyArgs = {};
	local tbl = addon:GetHistoricalSegmentsList();
	for i, v in pairs(tbl) do
		local t = addon:BuildOptionsTableForHistorySegment(i);
		if t then
			historyArgs["ctrl" .. i] = { name = v, order = i + 1, type = "group", args = t };
		end
	end
	addon.History:ClearDirty();
	return {
		HistorySelection = { name = "Logged Encounters", type = "group", order = 1, args = historyArgs },
	};
end

local function BuildOptionsTable(uiTypes, uiName, appName)
	local historyList = TryBuildHistoryList();
	if historyList then
		options.args.historyTab.args = historyList;
	end
	return options;
end

--[[----------------------------------------------------------------------------
	Chat commands
------------------------------------------------------------------------------]]
function addon:PrintRegenCalibration()
	local _, class = UnitClass("player");
	local key = class .. ":" .. tostring(UnitLevel("player"));
	local cal = self.hsw.db.global.regenCal and self.hsw.db.global.regenCal[key];
	if cal then
		self:Msg(string.format("Regen samples %s: Spirit %s -> %.2f mana/s, Spirit %s -> %s mana/s",
			key, tostring(cal[1]), cal[2], tostring(cal[3] or "?"), cal[4] and string.format("%.2f", cal[4]) or "?"));
	else
		self:Msg("No regen samples yet for " .. key);
	end
	self:Msg(string.format("Regen per Spirit in use: %.4f mana/s (default %.2f). Casting share now: %.0f%%.",
		self.RegenPerSpirit or 0, self.DefaultRegenPerSpirit, (self.ply_castpct or 0) * 100));
end

function addon:PrintPlayerStats()
	self:Msg(string.format("sp=%s crt=%.4f hst=%.4f int=%s spi=%s maxmana=%s",
		tostring(self.ply_sp), self.ply_crt or 0, self.ply_hst or 0, tostring(self.ply_int), tostring(self.ply_spi), tostring(self.ply_maxmana)));
	self:Msg(string.format("regen base=%.2f cast=%.2f castpct=%.2f intmult=%.3f spiritmult=%.3f",
		self.ply_regen_base or 0, self.ply_regen_cast or 0, self.ply_castpct or 0, self.ply_intmult or 1, self.ply_spiritmult or 1));
	self:Msg(string.format("CritConv=%s HasteConv=%s IntPerCrit=%s RegenPerSpirit=%.4f",
		tostring(self.CritConv), tostring(self.HasteConv), tostring(self.IntPerCrit), self.RegenPerSpirit or 0));
end

function hsw:ChatCommand(input)
	input = (input or ""):trim();
	if input == "" then
		if not hswOptionsFrame then self:OpenOptions() end
		return;
	end
	local cmd, arg = string.match(string.lower(input), "^(%S+)%s*(.*)$");
	if cmd == "show" then
		addon:Show();
	elseif cmd == "hide" then
		addon:Hide();
	elseif cmd == "lock" then
		addon:Lock();
	elseif cmd == "unlock" then
		addon:Unlock();
	elseif cmd == "debug" then
		local seg = addon.SegmentManager:Get(addon.currentSegment);
		if seg then seg:Debug() end
	elseif cmd == "start" then
		HSW_ENABLE_FOR_TESTING = true;
		addon:Show();
		addon:StartFight("test");
	elseif cmd == "end" then
		addon:EndFight();
	elseif cmd == "spec" then
		addon:Msg("Spec id: " .. tostring(addon:GetSpecId()) .. " (" .. tostring(spec_labels[addon:GetSpecId() or 0]) .. "), supported: " .. tostring(addon.StatParser:IsCurrentSpecSupported()));
	elseif cmd == "stats" then
		addon:PrintPlayerStats();
	elseif cmd == "regen" then
		addon:PrintRegenCalibration();
	elseif cmd == "discover" then
		addon.discoverSpells = (arg == "on");
		addon:Msg("Unknown-spell discovery " .. (addon.discoverSpells and "on" or "off") .. ".");
	else
		addon:Msg("/hsw [show|hide|lock|unlock|start|end|debug|spec|stats|regen|discover on|off]");
	end
end

--[[----------------------------------------------------------------------------
	History - store/retrieve historical segments
------------------------------------------------------------------------------]]
addon.History = addon.Queue.CreateHistoryQueue();

-- Stat weights of a segment relative to +Healing = 1: crit, haste (HPCT), Int, Spirit, MP5.
-- Int and Spirit add the live mana-based terms to the per-heal buckets.
function addon:GetStatsForSegment(segment)
	if not segment or not segment.t or segment.t.heal == 0 then
		return 1, 0, 0, 0, 0, 0;
	end
	local t = segment.t;
	return 1,
		t.crit / t.heal,
		segment:GetHasteHPCT() / t.heal,
		(t.int + segment:GetIntManaValue()) / t.heal,
		(t.spirit + segment:GetSpiritRegenValue()) / t.heal,
		segment:GetMP5() / t.heal;
end

local regions = { [1] = "US", [2] = "KR", [3] = "EU", [4] = "TW", [5] = "CN" };

function addon:AddHistoricalSegment(segment)
	if not segment or not segment.t or segment.t.heal == 0 then return end -- nothing healed
	if self:InRaidInstance() and not segment.instance.bossFight then return end -- raid trash

	local info = segment:GetInstanceInfo();
	local h = {};
	local duration = segment:GetDuration() or 0;
	local m = math.floor(duration / 60);
	local s = math.floor(duration - m * 60);
	local specId = self:GetSpecId();
	local pname, realm = UnitFullName("player");
	local regionID = GetCurrentRegion and GetCurrentRegion() or nil;

	h.tab = info.bossFight and "" or "    ";
	h.isDungeon = not self:InRaidInstance();
	h.Segment = segment.id;
	h.Duration = m .. ":" .. (s < 10 and "0" or "") .. s;
	h.Class = spec_labels[specId] or "Unknown";
	h.ClassName = UnitClass("player");
	h.SpecID = specId;
	h.Heal, h.Crt, h.Hst, h.Int, h.Spi, h.Mp5 = self:GetStatsForSegment(segment);
	h.DateTime = segment.startTimeStamp;
	h.Slot13 = segment.gear and segment.gear[13] or nil;
	h.Slot14 = segment.gear and segment.gear[14] or nil;

	-- stat points needed for +1% of this segment's healing
	local onePercent = segment.totalHealing / 100.0;
	local function perOnePercent(bucket)
		return bucket and bucket > 0 and onePercent / bucket or 0.0;
	end
	h.HealPct = perOnePercent(segment.t.heal);
	h.CrtPct  = perOnePercent(segment.t.crit);
	h.HstPct  = perOnePercent(segment:GetHasteHPCT());
	h.IntPct  = perOnePercent(segment.t.int + segment:GetIntManaValue());
	h.SpiPct  = perOnePercent(segment.t.spirit + segment:GetSpiritRegenValue());
	h.Mp5Pct  = perOnePercent(segment:GetMP5());

	h.Talents = segment.talentsSnapshot and segment.selectedTalents or {};
	h.Name = pname or "Unknown";
	h.Realm = realm or "Unknown";
	h.Region = regions[regionID] or "Unknown";

	self.History:Enqueue(h, segment);
end

--[[----------------------------------------------------------------------------
	Pawn export from the history tab
------------------------------------------------------------------------------]]
function addon:GetPawnStringFromHistory(i)
	local h = addon.History:Get(i or historySelected);
	if not h then return "" end
	local specIndex = addon.PawnSpecIndex[h.SpecID or 0] or 1;
	return self:GetPawnStringRaw(h.Segment, h.ClassName or h.Class, specIndex, h.Heal, h.Crt, h.Hst, h.Int, h.Spi, h.Mp5);
end

function addon:CreatePawnStringFromHistory()
	StaticPopup_Show(addon.PawnHistoryDialogName);
end

local function addExampleSegment()
	local s = addon.Segment.Create("Example Segment!");
	s:AllocateHeal(1, math.random(), math.random(), math.random(), math.random());
	addon:AddHistoricalSegment(s);
end

function addon:GetHistoricalSegmentsList()
	local t = {};
	local n = addon.History:Size();
	if n == 0 then
		addExampleSegment();
		n = addon.History:Size();
	end
	for i = 0, n - 1 do
		local h = addon.History:Get(i);
		if h then
			local segment_name = h.tab or "";
			local icon = spec_icons[h.SpecID];
			if icon then
				segment_name = segment_name .. " |T" .. icon .. ":18|t ";
			end
			t[i] = segment_name .. h.Segment .. " " .. h.Duration;
		end
	end
	return t;
end

--[[----------------------------------------------------------------------------
	Open Options
------------------------------------------------------------------------------]]
function hsw:OpenOptions()
	local AceGUI = LibStub("AceGUI-3.0");
	local hsw_frame = AceGUI:Create("Frame");
	hswOptionsFrame = hsw_frame;
	hsw_frame:SetTitle("Healer Stat Weights (Forever)");

	local version = addon.Compat.GetAddOnMetadata("HealerStatWeights", "Version");
	hsw_frame:SetStatusText("version " .. (version or "???"));

	hsw_frame:SetWidth(900);
	hsw_frame:SetHeight(640);
	hsw_frame:EnableResize(false);
	hsw_frame:SetLayout("Flow");
	hsw_frame:SetCallback("OnClose", function(w)
		AceGUI:Release(w);
		hswOptionsFrame = nil;
	end);
	hsw_frame:Show();

	local container = AceGUI:Create("SimpleGroup");
	container:SetFullHeight(true);
	container:SetFullWidth(true);
	LibStub("AceConfigDialog-3.0"):Open("HealerStatWeights", container);
	hsw_frame:AddChild(container);
end

--[[----------------------------------------------------------------------------
	Addon Initialized
------------------------------------------------------------------------------]]
function hsw:OnInitialize()
	self.db = LibStub("AceDB-3.0"):New("HSW_DB", defaults);

	-- History entries from the retail build (Int/Vrs/Mst/Lee keys) cannot be shown: wipe once.
	if self.db.global.schema ~= SCHEMA then
		wipe(self.db.global.history);
		self.db.global.front = 0;
		self.db.global.back = 0;
		self.db.global.schema = SCHEMA;
	end

	LibStub("AceConfigRegistry-3.0"):RegisterOptionsTable("HealerStatWeights", BuildOptionsTable, true);
	LibStub("AceConfigRegistry-3.0"):RegisterOptionsTable("HSW_Bliz", BlizOptionsTable);
	local optionsFrame, categoryID = LibStub("AceConfigDialog-3.0"):AddToBlizOptions("HSW_Bliz", "Healer Stat Weights (Forever)");
	optionsFrame.settingsCategoryID = categoryID; -- Settings.OpenToCategory wants the id, not the frame (Compat.OpenOptionsCategory)
	self.optionsFrame = optionsFrame;
	self:RegisterChatCommand("hsw", "ChatCommand");
end

addon.SegmentLabels = SegmentLabels;
addon.hsw = hsw;
