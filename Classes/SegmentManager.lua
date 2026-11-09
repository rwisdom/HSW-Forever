local name, addon = ...;
local ids = {};



--[[----------------------------------------------------------------------------
	Segment Manager: 
	
	Contains queue of most-recent Segments, as well as a "Total" Segment.
------------------------------------------------------------------------------]]
local SegmentManager = {
	segments = {},
	front=0, --front of queue
	back=0, --back of queue
	Total = addon.Segment.Create("Total");
};
SegmentManager.Total.startTime = -1; -- live only during a fight (StartFight)



--[[----------------------------------------------------------------------------
	ResetTotalSegment - Resets the "Total" segment
------------------------------------------------------------------------------]]
function SegmentManager:ResetTotalSegment() --reset the total segment
	self.Total = addon.Segment.Create("Total");
	self.Total.startTime = -1;
end



--[[----------------------------------------------------------------------------
	ResetAllSegments - Resets the "Total" segment & Removes all other segments
------------------------------------------------------------------------------]]
function SegmentManager:ResetAllSegments()
	if ( not addon.inCombat ) then
		self:ResetTotalSegment();
		while (self:Size() > 0) do
			self:Dequeue()
		end
		wipe(ids); -- numbering ("Boss(2)") starts over with the list
	end
end



--[[----------------------------------------------------------------------------
	Enqueue - Create & add a new segment to the front of the queue. isBossFight
	marks a segment that is logged even as raid trash (encounters, manual segments).
------------------------------------------------------------------------------]]
function SegmentManager:Enqueue(id, isBossFight)
	self.front = self.front + 1;
	self.segments[self.front] = addon.Segment.Create(id or "Trash"); -- unnamed until a mob name is known

	if ( id ) then
		self:SetCurrentId(id, isBossFight);
	end
	
	if ( self:Size() > addon.hsw.db.global.maxSegments ) then
		self:Dequeue();
	end	
end



--[[----------------------------------------------------------------------------
	Dequeue - Remove the segment at back of the queue
------------------------------------------------------------------------------]]
function SegmentManager:Dequeue()
	if ( self:Size() > 0 ) then
		self.back = self.back + 1;
		self.segments[self.back] = nil;
	end
end



--[[----------------------------------------------------------------------------
	Size - Return the size of the queue (number of segments)
------------------------------------------------------------------------------]]
function SegmentManager:Size()
	return self.front - self.back;
end



--[[----------------------------------------------------------------------------
	Get - Get ith most-recent segment, or the "Total" segment. 0-based.
------------------------------------------------------------------------------]]
function SegmentManager:Get(i)
	if ( i == "Total" ) then
		return self.Total;
	end
	
	if ( tonumber(i) and self.segments[self.front - i] ) then
		return self.segments[self.front-i];
	end
	
	return nil;
end



--[[----------------------------------------------------------------------------
	ForEachLive - Calls fn(segment) on the current fight and the Total segment,
	the two every heal, cast and tick of time is credited to.
------------------------------------------------------------------------------]]
function SegmentManager:ForEachLive(fn)
	local cur_seg = self:Get(0);
	if cur_seg then fn(cur_seg) end
	fn(self.Total);
end



--[[----------------------------------------------------------------------------
	SetId - Update the name of the current segment & boss flag
------------------------------------------------------------------------------]]
function SegmentManager:SetCurrentId(newId,isBossFight)
	local seg = self.segments[self.front];
	if ( newId and newId ~= "Trash" and newId ~= "Total" and not seg.nameSet ) then
		seg.bossFight = isBossFight and true or false;
		self:Name(seg, newId);
	end
end

--[[----------------------------------------------------------------------------
	Name - Give a still-unnamed segment its name, numbered "(2)" for a repeat. Used
	at fight start (SetCurrentId) and at pricing for a fight whose hostile name was
	secret, from the meter session's name (addon:FinalizePending).
------------------------------------------------------------------------------]]
function SegmentManager:Name(seg, newId)
	if ( not newId or newId == "Trash" or newId == "Total" or seg.nameSet ) then return end
	ids[newId] = ( ids[newId] or 0 ) + 1;
	if ( ids[newId] > 1 ) then
		seg.id = newId .. "(" .. tostring(ids[newId]) .. ")";
	else
		seg.id = newId;
	end
	seg.nameSet = true;
end



addon.SegmentManager = SegmentManager;