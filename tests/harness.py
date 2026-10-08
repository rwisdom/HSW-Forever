"""Loads addon Lua files into a Lua 5.1 runtime with the WoW API stubs from tests/wow_stub.lua."""
import pathlib

try:
    from lupa.lua51 import LuaRuntime
except ImportError:  # older lupa builds expose only the default runtime
    from lupa import LuaRuntime

ROOT = pathlib.Path(__file__).resolve().parent.parent

CORE_FILES = [
    "Classes/Compat.lua",
    "Classes/Util.lua",
    "Classes/BuffTracker.lua",
    "Classes/CastTracker.lua",
    "Classes/Segment.lua",
    "Classes/SegmentManager.lua",
    "Classes/StatParser.lua",
    "Classes/UnitManager.lua",
    "Classes/HealMatcher.lua",
    "Classes/Queues.lua",
    "Classes/OptionsBuilder.lua",
    "Parsers/Spells.lua",
    "Parsers/Spells_Generated.lua",
    "Parsers/Spells_Manual.lua",
    "Parsers/Talents_Generated.lua",
]


def load(files=CORE_FILES, setup=""):
    """Returns (lua_runtime, addon_table). `setup` is Lua run after the stub, before addon files."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute((ROOT / "tests" / "wow_stub.lua").read_text(encoding="utf-8"))
    if setup:
        lua.execute(setup)
    run_file = lua.eval("""function(path, src)
        local chunk, err = (loadstring or load)(src, "@" .. path)
        if not chunk then error(err) end
        return chunk("HealerStatWeights", HSW_TEST_ADDON)
    end""")
    for rel in files:
        run_file(rel, (ROOT / rel).read_text(encoding="utf-8"))
    return lua, lua.globals().HSW_TEST_ADDON
