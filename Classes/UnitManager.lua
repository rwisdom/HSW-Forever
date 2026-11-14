local name,addon=...;

local UnitManager = {
	units = {}
};



--[[----------------------------------------------------------------------------
	Stored Strings
------------------------------------------------------------------------------]]
local party = {};
local raid = {};
local partypet = {};
local raidpet = {};
local ply = "player";
do
	for i=1,5,1 do party[i] = "party"..i; partypet[i] = "partypet"..i end
	for i=1,40,1 do raid[i] = "raid"..i; raidpet[i] = "raidpet"..i end
end



--[[----------------------------------------------------------------------------
	Cache() - GUID -> unit token, unit name -> unit token, and the group's names,
	for the player, the group and the group's pets: the only units our heals land on.
	Names matter on Forever: UNIT_SPELLCAST_SENT reports the cast target by name
	(a pet's as a secret string: HealMatcher finds it here by the selected unit's GUID).
------------------------------------------------------------------------------]]
function UnitManager:Cache()
	self.units = {};
	self.names = {};
	self.groupNames = {};
	local P = addon.Compat.PlainString;
	local function add(token)
		local g = P(UnitGUID(token)); -- secret for a unit reached through a hostile one: unusable as a key
		if not g or self.units[g] then return end -- the player also appears as raidN
		self.units[g] = token;
		local n = P(UnitName(token));
		if n then
			self.names[n] = token;
			table.insert(self.groupNames, n);
		end
	end
	if UnitInRaid(ply) then
		for i = 1, GetNumGroupMembers() do add(raid[i]); add(raidpet[i]) end
	elseif UnitInParty(ply) then
		for i = 1, GetNumGroupMembers() do add(party[i]); add(partypet[i]) end
	end
	add(ply);
end

--[[----------------------------------------------------------------------------
	Find(guid) - unit token for a GUID. FindByName(name) - unit token for a name.
	GroupNames() - names of the player and every group member (party-wide HoTs).
------------------------------------------------------------------------------]]
function UnitManager:Find(guid)
	return self.units[guid];
end

function UnitManager:FindByName(unitName)
	return self.names and self.names[unitName] or nil;
end

function UnitManager:GroupNames()
	return self.groupNames or {};
end



addon.UnitManager = UnitManager;
