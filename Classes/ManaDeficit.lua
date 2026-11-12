local name, addon = ...;

--[[----------------------------------------------------------------------------
	ManaDeficit - mana below a full bar, estimated. Current mana is a secret value
	on Forever (probe 2026-11-10), so the addon walks the bar itself: a cast raises
	the deficit; regen, crit returns, potions and drinks lower it; it stops at a
	full bar (0) and at an empty one (max mana). It runs in and out of combat, so a
	pull that starts below full starts with what the last one left. A fight's share
	of the mana pool is how far the deficit rose over the fight (addon:EndFight).
	Nothing ever corrects it against the real bar: Mana Tide, buff MP5 and the like
	are not seen, and the error lasts until the estimated bar is full again.
------------------------------------------------------------------------------]]
local ManaDeficit = { deficit = 0, drinkRate = 0 };

-- Brings the deficit up to `now` and returns it: Spirit regen at the base rate outside the
-- five-second rule and at the casting share inside it, gear MP5 and a drink throughout. The first
-- call starts the clock from a full bar (login, /reload).
function ManaDeficit:Advance(now)
	now = now or GetTime();
	local dt = now - (self.last or now);
	if dt < 0 then return self.deficit end
	local sinceSpend = self.last and self.lastSpend and self.last - self.lastSpend or math.huge;
	local inFSR = math.max(0, math.min(dt, addon.FSR_SECONDS - sinceSpend));
	local regen = (addon.ply_regen_base or 0) * (dt - inFSR + (addon.ply_castpct or 0) * inFSR)
		+ ((addon.ply_mp5 or 0) / 5 + self.drinkRate) * dt;
	self.deficit = math.max(0, self.deficit - regen);
	self.last = now;
	return self.deficit;
end

-- A cast that cost mana, in or out of combat: the five-second rule restarts.
function ManaDeficit:Spend(mana, now)
	now = now or GetTime();
	self:Advance(now);
	local max = addon.ply_maxmana or 0;
	self.deficit = self.deficit + mana;
	if max > 0 and self.deficit > max then self.deficit = max end
	self.lastSpend = now;
end

-- Mana that came back at once: a crit return, a potion.
function ManaDeficit:Gain(mana, now)
	self:Advance(now);
	self.deficit = math.max(0, self.deficit - mana);
end

function ManaDeficit:SetDrinkRate(rate, now)
	self:Advance(now); -- the time so far ran at the old rate
	self.drinkRate = rate;
end

-- Share of the mana pool a fight emptied, 0 to 1: how far the deficit rose from `from` to `to`.
function ManaDeficit.Share(from, to)
	local max = addon.ply_maxmana or 0;
	if max <= 0 then return 0 end
	return math.max(0, math.min(1, (to - from) / max));
end

-- Mana per second a buff restores, by its tooltip. Seen in game 2026-11-11: the Drink buff (432)
-- reads "Restores 835 mana over 24 sec.", its item (Melon Juice) "Restores 34 mana per second.";
-- both wordings are read. Some drinks restore a share of the bar instead,
-- "N% of your mana per second" (wording reported 2026-11-11, not seen): that one follows max mana.
-- 0 for any other text. nil while the text cannot be read or is still empty; it is asked again
-- then, and kept per spell id once it reads.
local drinkRates, drinkShares = {}, {}; -- per spell id: mana per second, and share of max mana per second
function ManaDeficit.DrinkRateOf(spellID)
	if not drinkRates[spellID] then
		local text = addon.Compat.GetSpellDescription(spellID);
		if not text or text == "" then return nil end
		local n, secs = text:match("([%d,%.]+) mana over (%d+) sec");
		local perSecond = text:match("([%d,%.]+) mana per second");
		if perSecond then n, secs = perSecond, 1 end
		n, secs = n and tonumber((n:gsub(",", ""))), tonumber(secs);
		drinkRates[spellID] = n and secs > 0 and n / secs or 0;
		drinkShares[spellID] = (tonumber(text:match("([%d%.]+)%% of [%a ]*mana per second")) or 0) / 100;
	end
	return drinkRates[spellID] + drinkShares[spellID] * (addon.ply_maxmana or 0);
end

-- The player's buffs (UNIT_AURA): the drink rate is the sum over the buffs up. In combat the
-- client refuses aura reads and the rate stays what it was, 0 since the pull.
function ManaDeficit:ScanDrink(now)
	local rate = 0;
	for i = 1, 40 do
		local _, _, _, id, blocked = addon.Compat.UnitAura("player", i);
		if blocked then return end
		if not id then break end
		rate = rate + (ManaDeficit.DrinkRateOf(id) or 0);
	end
	self:SetDrinkRate(rate, now);
end

addon.ManaDeficit = ManaDeficit;
