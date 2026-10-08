local name,addon=...;

local UnitManager = {
	units = {}
};



--[[----------------------------------------------------------------------------
	Stored Strings
------------------------------------------------------------------------------]]
local party = {};
local raid = {};
local boss = {};
local ply = "player";
do
	for i=1,5,1 do party[i] = "party"..i end
	for i=1,40,1 do raid[i] = "raid"..i end
	for i=1,10,1 do boss[i] = "boss"..i end
end
	


--[[----------------------------------------------------------------------------
	Cache() - GUID -> unit token, unit name -> unit token, and the group's names.
	Names matter on Forever: UNIT_SPELLCAST_SENT reports the cast target by name.
------------------------------------------------------------------------------]]
function UnitManager:Cache()
	self.units = {};
	self.names = {};
	self.groupNames = {};
	local function add(token, inGroup)
		local g = UnitGUID(token);
		if not g or self.units[g] then return end -- the player also appears as raidN
		self.units[g] = token;
		local n = UnitName(token);
		if n then
			self.names[n] = token;
			if inGroup then table.insert(self.groupNames, n) end
		end
	end
	if UnitInRaid(ply) then
		for i = 1, GetNumGroupMembers() do add(raid[i], true) end
	elseif UnitInParty(ply) then
		for i = 1, GetNumGroupMembers() do add(party[i], true) end
	end
	for i = 1, 10 do add(boss[i], false) end
	add(ply, true);
end

--[[----------------------------------------------------------------------------
	Find(guid) - unit token for a GUID. FindByName(name) - unit token for a name.
	GroupNames() - names of the player and every group member (party-wide HoTs).
------------------------------------------------------------------------------]]
function UnitManager:Find(guid)
	if not self.units[guid] then
		local boss1guid = UnitGUID("boss1");
		if guid == boss1guid then
			self.units[guid] = "boss1";
		end
	end
	return self.units[guid];
end

function UnitManager:FindByName(unitName)
	return self.names and self.names[unitName] or nil;
end

function UnitManager:GroupNames()
	return self.groupNames or {};
end



addon.UnitManager = UnitManager;
