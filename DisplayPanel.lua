local name, addon = ...;
local media = LibStub("LibSharedMedia-3.0");

--[[----------------------------------------------------------------------------
	Strings & Patterns
------------------------------------------------------------------------------]]
local pattern_title = "%s";
local pattern_left = "+Healing\nCrit Rating\nHaste (HPCT)\nIntellect\nSpirit\nMP5";
local pattern_right = "%.2f\n%.2f\n%.2f\n%.2f\n%.2f\n%.2f";
-- Pawn stat identifiers as used by Classic-family Pawn; verify on Forever (Task 17).
local pawn_pattern = [[( Pawn: v1: "%s": Class=%s, Spec=%s, HealingPower=%.2f, SpellCritRating=%.2f, SpellHaste=%.2f, Intellect=%.2f, Spirit=%.2f, Mp5=%.2f)]];
local pawn_str_name = "%s-HSW-%s";
local pawn_title = "Pawn String (Ctrl+A to select all, Ctrl+C to copy):";
local pawn_dialog_name = "HSW_GETPAWNSTRING";
local clearsegments_dialog_name = "HSW_CLEARALLSEGMENTS";
local clearsegments_title = "Clear all segments?";
local btn_size = 16;

local function forEachSegment(fn)
	local cur_seg = addon.SegmentManager:Get(0);
	local ttl_seg = addon.SegmentManager:Get("Total");
	if cur_seg then fn(cur_seg) end
	if ttl_seg then fn(ttl_seg) end
end

--[[----------------------------------------------------------------------------
	Display updates (safe to call before SetupFrame)
------------------------------------------------------------------------------]]
function addon:UpdateDisplayStats()
	if self.inCombat then -- bring the five-second-rule split up to date before showing Spirit
		local now = GetTime();
		forEachSegment(function(seg) seg:AccumulateFSR(now) end);
	end
	if not self.frame then return end
	self.frame.textR:SetFormattedText(pattern_right, self:GetStatsForDisplay());
end

function addon:UpdateDisplayTitle(title)
	if not self.frame then return end
	self.frame.textTitle:SetFormattedText(pattern_title, title);
end

function addon:UpdateDisplayLabels()
	if not self.frame then return end
	self.frame.textL:SetText(pattern_left);
end

function addon:SetCurrentSegment(segmentID)
	self.currentSegment = segmentID;
	local id;
	if segmentID == 0 then
		id = "Current Fight";
	elseif segmentID == "Total" then
		id = "Total";
	else
		local segment = self.SegmentManager:Get(segmentID);
		id = segment and segment.id or "Unknown";
	end
	self:UpdateDisplayLabels();
	self:UpdateDisplayStats();
	self:UpdateDisplayTitle(id);
end

-- heal, crit, haste, int, spirit, mp5 of the displayed segment (+Healing = 1)
function addon:GetStatsForDisplay()
	return self:GetStatsForSegment(self.SegmentManager:Get(self.currentSegment));
end

--[[----------------------------------------------------------------------------
	SegmentMenu - segment selection dropdown
------------------------------------------------------------------------------]]
function addon:SegmentMenu()
	local menu = {
		{ text = "Select a Segment", isTitle = true },
		{ text = "Total", func = function() addon:SetCurrentSegment("Total") end },
		{ text = "Current Fight", func = function() addon:SetCurrentSegment(0) end },
	};
	for i = 1, self.SegmentManager:Size() - 1 do
		local segment = self.SegmentManager:Get(i);
		if segment then
			table.insert(menu, { text = segment.id, func = function() addon:SetCurrentSegment(i) end });
		end
	end
	if self.currentSegment == "Total" then
		menu[2].checked = true;
	elseif not self.currentSegment or self.currentSegment == 0 then
		menu[3].checked = true;
	elseif menu[3 + self.currentSegment] then
		menu[3 + self.currentSegment].checked = true;
	end
	self.menuFrame = self.menuFrame or CreateFrame("Frame", "HSW_SegmentMenu_Frame", UIParent, "UIDropDownMenuTemplate");
	addon.Compat.ShowContextMenu(menu, self.menuFrame);
end

--[[----------------------------------------------------------------------------
	Show / Hide / Msg
------------------------------------------------------------------------------]]
function addon:Show()
	addon.frameVisible = true;
	self:SetCurrentSegment(self.currentSegment or "Total");
	if self.frame then self.frame:Show() end
end

function addon:Hide()
	addon.frameVisible = false;
	if self.frame then self.frame:Hide() end
end

function addon:Msg(s)
	if s then
		DEFAULT_CHAT_FRAME:AddMessage("|cff00fbf6[HSW]|r " .. tostring(s), 1, 1, 1);
	end
end

--[[----------------------------------------------------------------------------
	Content gates - by instance type (no retail difficulty ids on Forever)
------------------------------------------------------------------------------]]
function addon:Enabled()
	if not self.StatParser:IsCurrentSpecSupported() then return false end
	local db = self.hsw.db.global;
	if HSW_ENABLE_FOR_TESTING or db.alwaysEnabled then return true end
	local _, instType = IsInInstance();
	if instType == "party" then return db.enabledInDungeons and true or false end
	if instType == "raid" then return db.enabledInRaids and true or false end
	if instType == "pvp" then return db.enabledInBattlegrounds and true or false end
	return false;
end

function addon:InRaidInstance()
	local _, instType = IsInInstance();
	return instType == "raid";
end

function addon:AdjustVisibility()
	if not self.hsw.db.global.neverShow and (self:Enabled() or self.hsw.db.global.alwaysShow) then
		self:Show();
	else
		self:Hide();
	end
end

function addon:Lock()
	self:Msg("Healer Stat Weights frame locked.");
	self.hsw.db.global.frameLocked = true;
	if self.frame then
		self.frame:EnableMouse(false);
		self.frame:SetMovable(false);
	end
end

function addon:Unlock()
	self:Msg("Healer Stat Weights frame unlocked.");
	self.hsw.db.global.frameLocked = false;
	if self.frame then
		self.frame:EnableMouse(true);
		self.frame:SetMovable(true);
	end
end

--[[----------------------------------------------------------------------------
	Pawn String - dialog with the Pawn import string
------------------------------------------------------------------------------]]
function addon:GetPawnStringRaw(title, class, specIndex, heal, crt, hst, int, spi, mp5)
	return string.format(pawn_pattern, title, class, specIndex, heal, crt, hst, int, spi, mp5);
end

function addon:GetPawnString()
	local segment = self.SegmentManager:Get(self.currentSegment);
	local class = UnitClass("player");
	local specIndex = addon.PawnSpecIndex[self:GetSpecId() or 0] or 1;
	local title = string.format(pawn_str_name, class, segment and segment.id or "Unknown");
	return self:GetPawnStringRaw(title, class, specIndex, self:GetStatsForDisplay());
end

addon.PawnHistoryDialogName = pawn_dialog_name .. "_HISTORY";
StaticPopupDialogs[addon.PawnHistoryDialogName] = {
	text = pawn_title,
	button1 = OKAY,
	button2 = CANCEL,
	hasEditBox = true,
	editBoxWidth = 600,
	maxLetters = 9999,
	OnShow = function(self, data)
		local s = addon:GetPawnStringFromHistory();
		print(s);
		self.editBox:SetText(s);
	end,
	timeout = 0,
	exclusive = 1,
	hideOnEscape = 1,
	whileDead = 1,
};

StaticPopupDialogs[pawn_dialog_name] = {
	text = pawn_title,
	button1 = OKAY,
	button2 = CANCEL,
	hasEditBox = true,
	editBoxWidth = 600,
	maxLetters = 9999,
	OnShow = function(self, data)
		local s = addon:GetPawnString();
		print(s);
		self.editBox:SetText(s);
	end,
	timeout = 0,
	exclusive = 1,
	hideOnEscape = 1,
	whileDead = 1,
};

--[[----------------------------------------------------------------------------
	Clear All Segments - confirmation dialog
------------------------------------------------------------------------------]]
StaticPopupDialogs[clearsegments_dialog_name] = {
	text = clearsegments_title,
	button1 = YES,
	button2 = NO,
	OnAccept = function()
		addon.SegmentManager:ResetAllSegments();
		addon:SetCurrentSegment(0);
	end,
	timeout = 0,
	exclusive = 1,
	hideOnEscape = 1,
	whileDead = 1,
};

--[[----------------------------------------------------------------------------
	StartFight / EndFight
------------------------------------------------------------------------------]]
function addon:StartFight(id)
	if self.inCombat or not self:Enabled() then return end
	self:UpdatePlayerStats();
	self.UnitManager:Cache();
	self.HealMatcher:Reset();
	self.SegmentManager:Enqueue(id);

	-- the Total segment is live for the duration of every fight
	local cur_seg = self.SegmentManager:Get(0);
	local ttl_seg = self.SegmentManager:Get("Total");
	if ttl_seg and cur_seg then
		ttl_seg.startTime = cur_seg.startTime;
		ttl_seg.fsrLastAccum = cur_seg.startTime;
	end

	self.inCombat = true;
	self:AdjustVisibility();
end

function addon:EndFight()
	if not self.inCombat then return end
	self.inCombat = false;
	local cur_seg = self.SegmentManager:Get(0);
	local ttl_seg = self.SegmentManager:Get("Total");
	if cur_seg then
		cur_seg:End();
		self:AddHistoricalSegment(cur_seg);
	end
	if ttl_seg then
		ttl_seg:End();
	end
end

--[[----------------------------------------------------------------------------
	Frame helpers
------------------------------------------------------------------------------]]
local function makeButton(parent, title, description, tex, clickfunc)
	local btn = CreateFrame("Button", nil, parent);
	btn.title = title;
	btn:SetFrameLevel(5);
	btn:ClearAllPoints();
	btn:SetHeight(btn_size);
	btn:SetWidth(btn_size);
	btn:SetNormalTexture(tex);
	btn:SetHighlightTexture(tex, "ADD");
	btn:SetAlpha(0.35);
	btn:RegisterForClicks("LeftButtonUp", "RightButtonUp");
	btn:SetScript("OnClick", clickfunc);
	btn:SetScript("OnEnter", function(this)
		GameTooltip_SetDefaultAnchor(GameTooltip, this);
		GameTooltip:SetText(title);
		GameTooltip:AddLine(description, 1, 1, 1, true);
		GameTooltip:Show();
	end);
	btn:SetScript("OnLeave", function() GameTooltip:Hide() end);
	btn:Show();
	table.insert(parent.buttons, btn);
end

function addon:AdjustFontSizes()
	local size = self.hsw.db.global.fontSize;
	local p = self.frame.textL:GetFont();
	self.frame.textL:SetFont(p, size, "OUTLINE");
	p = self.frame.textR:GetFont();
	self.frame.textR:SetFont(p, size, "OUTLINE");
	p = self.frame.textTitle:GetFont();
	self.frame.textTitle:SetFont(p, size + 2, "OUTLINE");
end

function addon:AdjustFontColor()
	local c = self.hsw.db.global.fontColor;
	self.frame.textL:SetTextColor(c.r, c.g, c.b, c.a);
	self.frame.textR:SetTextColor(c.r, c.g, c.b, c.a);
	self.frame.textTitle:SetTextColor(c.r, c.g, c.b, c.a);
end

function addon:AdjustWidth(newWidth)
	self.frame:SetWidth(newWidth);
	self.frame.textTitle:SetWidth(newWidth - btn_size * 4);
end

function addon:AdjustFonts()
	local p, s, f = self.frame.textL:GetFont();
	local str = self.hsw.db.global.fontStr;
	local path = str and media:Fetch("font", str) or p;
	self.frame.textL:SetFont(path, s, f);
	p, s, f = self.frame.textR:GetFont();
	self.frame.textR:SetFont(path, s, f);
	p, s, f = self.frame.textTitle:GetFont();
	self.frame.textTitle:SetFont(path, s, f);
end

function addon:ResetFramePosition()
	self.hsw.db.global.frameX = nil;
	self.frame:ClearAllPoints();
	self.frame:SetPoint("CENTER", 0, 0);
end

--[[----------------------------------------------------------------------------
	SetupFrame - the stats panel
------------------------------------------------------------------------------]]
function addon:SetupFrame()
	if self.frame then return end
	local db = self.hsw.db.global;
	local W = db.frameWidth or 192;
	local H = 128;

	local frame = CreateFrame("Frame", nil, UIParent);
	frame:SetWidth(W);
	frame:SetHeight(H);
	frame:ClearAllPoints();
	if db.frameX then
		frame:SetPoint("BOTTOMLEFT", db.frameX or 0, db.frameY or 0);
	else
		frame:SetPoint("CENTER", 0, 0);
	end
	frame:EnableMouse(not db.frameLocked);
	frame:SetMovable(not db.frameLocked);
	frame:RegisterForDrag("LeftButton");
	frame:SetScript("OnDragStart", frame.StartMoving);
	frame:SetScript("OnDragStop", function(f)
		f:StopMovingOrSizing();
		db.frameX = f:GetLeft();
		db.frameY = f:GetBottom();
	end);

	local text = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal");
	text:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, -btn_size);
	text:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0);
	text:SetJustifyH("LEFT");
	text:SetJustifyV("TOP");
	text:SetFontObject(GameFontWhite);
	text:SetShadowColor(0, 0, 0, .7);
	text:SetShadowOffset(1, 1);
	local p = text:GetFont();
	text:SetFont(p, db.fontSize, "OUTLINE");
	frame.textL = text;

	text = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal");
	text:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, -btn_size);
	text:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0);
	text:SetJustifyH("RIGHT");
	text:SetJustifyV("TOP");
	text:SetFontObject(GameFontWhite);
	p = text:GetFont();
	text:SetFont(p, db.fontSize, "OUTLINE");
	frame.textR = text;
	frame.buttons = {};

	makeButton(frame, "Clear", "Clear out all segments.", "Interface\\Buttons\\UI-StopButton", function()
		if not addon.inCombat then
			StaticPopup_Show(clearsegments_dialog_name);
		else
			addon:Msg("Cannot clear segments while in combat.");
		end
	end);
	makeButton(frame, "Configure", "Open the options menu", "Interface\\Buttons\\UI-OptionsButton", function()
		addon.Compat.OpenOptionsCategory(self.hsw.optionsFrame);
	end);
	makeButton(frame, "Export", "Get the Pawn string for the current stat weights.", "Interface\\Buttons\\UI-GuildButton-MOTD-Up", function()
		StaticPopup_Show(pawn_dialog_name);
	end);
	makeButton(frame, "Segment", "Select a segment", "Interface\\Buttons\\UI-GuildButton-PublicNote-Up", function()
		self:SegmentMenu();
	end);

	text = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal");
	text:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0);
	text:SetJustifyH("LEFT");
	text:SetFontObject(GameFontWhite);
	p = text:GetFont();
	text:SetFont(p, db.fontSize + 2, "OUTLINE");
	text:SetWidth(W - btn_size * 4);
	text:SetHeight(16);
	frame.textTitle = text;

	for i = 1, #frame.buttons do
		frame.buttons[i]:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -btn_size * (i - 1), 0);
	end
	self.frame = frame;

	self:AdjustFontColor();
	self:AdjustFonts();
	self:SetupUnitEvents();
	self:SetCurrentSegment(self.currentSegment or "Total");
end
