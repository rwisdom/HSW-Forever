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
local ManaDeficit = { deficit = 0, drinkRate = 0, buffs = {} };

-- Mana per second from lasting buffs that the client's regen rates do not hold. `buffs` lists what
-- each buff's text says. Some buffs are in the rates already (Might of Stormwind's 10 MP5, seen
-- 2026-11-11) and show in ply_flat_buff; others are not (Blessing of Wisdom, 2026-11-12). A buff
-- counts as held by the rates when their flat part equals its rate, or equals all of them
-- together; a flat part that fits neither belongs to a buff whose text was not understood.
function ManaDeficit:UnseenBuffRate()
	local held, total = addon.ply_flat_buff or 0, 0;
	for _, rate in ipairs(self.buffs) do total = total + rate end
	if math.abs(total - held) < 0.05 then return 0 end
	for _, rate in ipairs(self.buffs) do
		if math.abs(rate - held) < 0.05 then return total - rate end
	end
	return total;
end

-- A mana event of the player's (UNIT_POWER_UPDATE): only its time is kept. The client sends one
-- for every change of the bar, in and out of combat, and none while the bar is full (probe
-- 2026-11-12), which is the one sign of the real bar the addon gets.
function ManaDeficit:OnPower(now)
	self.lastPower = now;
end

-- Seconds without a mana event that mean a full bar. While the bar fills, Spirit regen sends one
-- every 2.0 to 2.1 s, inside the five-second rule too, and Blessing of Wisdom one every 5 s; at a
-- full bar neither sends any (probe 2026-11-12). 6 is three regen ticks.
local FULL_AFTER = 6;

-- True when the bar must be full: no mana event for FULL_AFTER seconds, counted from the later of
-- the last one and the end of the five-second rule after the last spend (inside it some classes
-- regenerate nothing, so silence there proves nothing). Trusted only when the last spend's own
-- mana event arrived, in case the client withholds the event somewhere.
function ManaDeficit:IsFull(now)
	if not self.lastPower or not self.lastSpend or self.lastPower < self.lastSpend - 0.5 then return false end
	return now - math.max(self.lastPower, self.lastSpend + addon.FSR_SECONDS) >= FULL_AFTER;
end

-- Brings the deficit up to `now` and returns it: Spirit regen at the base rate outside the
-- five-second rule and at the casting share inside it; gear MP5, a drink and mana buffs
-- throughout. A bar known to be full sets it to 0, whatever the count says: that clears what
-- the count could not see (Mana Spring, an Innervate, a level). The first call starts the clock
-- from a full bar (login, /reload).
function ManaDeficit:Advance(now)
	now = now or GetTime();
	local dt = now - (self.last or now);
	if dt < 0 then return self.deficit end
	if self:IsFull(now) then
		self.deficit, self.last = 0, now;
		return 0;
	end
	local sinceSpend = self.last and self.lastSpend and self.last - self.lastSpend or math.huge;
	local inFSR = math.max(0, math.min(dt, addon.FSR_SECONDS - sinceSpend));
	local regen = (addon.ply_regen_base or 0) * (dt - inFSR + (addon.ply_castpct or 0) * inFSR)
		+ ((addon.ply_mp5 or 0) / 5 + self.drinkRate + self:UnseenBuffRate()) * dt;
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
-- A lasting buff reads "... restoring 18 mana every 5 seconds ..." (Blessing of Wisdom, 19850, seen
-- 2026-11-12). 0 for any other text. nil while the text cannot be read or is still empty; it is
-- asked again then, and kept per spell id once it reads.
local drinkRates, drinkShares, buffRates = {}, {}, {}; -- per spell id: a drink's mana per second and share of max mana per second, a lasting buff's mana per second
local function number(s) return s and tonumber((s:gsub(",", ""))) end
local function readText(spellID)
	if drinkRates[spellID] then return true end
	local text = addon.Compat.GetSpellDescription(spellID);
	if not text or text == "" then return false end
	local n, secs = text:match("([%d,%.]+) mana over (%d+) sec");
	local perSecond = text:match("([%d,%.]+) mana per second");
	if perSecond then n, secs = perSecond, 1 end
	n, secs = number(n), tonumber(secs);
	drinkRates[spellID] = n and secs > 0 and n / secs or 0;
	drinkShares[spellID] = (tonumber(text:match("([%d%.]+)%% of [%a ]*mana per second")) or 0) / 100;
	n, secs = text:match("([%d,%.]+) mana every (%d+) sec");
	n, secs = number(n), tonumber(secs);
	buffRates[spellID] = n and secs > 0 and n / secs or 0;
	return true;
end

-- A drink: it ends when combat starts.
function ManaDeficit.DrinkRateOf(spellID)
	if not readText(spellID) then return nil end
	return drinkRates[spellID] + drinkShares[spellID] * (addon.ply_maxmana or 0);
end

-- A lasting buff: it stays through combat.
function ManaDeficit.BuffRateOf(spellID)
	if not readText(spellID) then return nil end
	return buffRates[spellID];
end

-- The player's buffs (UNIT_AURA, PLAYER_ENTERING_WORLD): the drink rate is the sum over the buffs
-- up, `buffs` the rates of the lasting ones. In combat the client refuses aura reads and both stay
-- what they were: the drink 0 since the pull, a blessing as last seen (one cast or run out
-- mid-fight is missed).
function ManaDeficit:ScanBuffs(now)
	local drink, lasting = 0, {};
	for i = 1, 40 do
		local _, _, _, id, blocked = addon.Compat.UnitAura("player", i);
		if blocked then return end
		if not id then break end
		drink = drink + (ManaDeficit.DrinkRateOf(id) or 0);
		local rate = ManaDeficit.BuffRateOf(id);
		if rate and rate > 0 then lasting[#lasting + 1] = rate end
	end
	self:SetDrinkRate(drink, now); -- the time so far ran at the old rates
	self.buffs = lasting;
end

addon.ManaDeficit = ManaDeficit;
