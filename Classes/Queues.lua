local name, addon = ...;
local Queue = {};

local copy = addon.Util.CopyTable;

--[[----------------------------------------------------------------------------
	CreateHistoryQueue - bounded queue of history entries stored in the saved
	variables (db.global.history, front, back).
------------------------------------------------------------------------------]]
function Queue.CreateHistoryQueue()
	local t = { Dirty = true };
	t.Enqueue = function(self, item)
		local g = addon.hsw.db.global;
		g.front = g.front + 1;
		g.history[g.front] = copy(item);
		while self:Size() > g.historySize do
			self:Dequeue();
		end
		self.Dirty = true;
	end
	t.Dequeue = function(self)
		local g = addon.hsw.db.global;
		if self:Size() > 0 then
			g.back = g.back + 1;
			g.history[g.back] = nil;
		end
	end
	t.ClearDirty = function(self) self.Dirty = false end
	t.GetDirty = function(self) return self.Dirty end
	t.Size = function(self)
		local g = addon.hsw.db.global;
		return g.front - g.back;
	end
	t.Get = function(self, i)
		local g = addon.hsw.db.global;
		return g.history[g.front - i];
	end
	return t;
end

addon.Queue = Queue;
