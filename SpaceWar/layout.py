"""SpaceWar-specific ROM and RAM locations and launch options."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent

ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.json"
GAME_ENTRY = 0x2379DD
STATE_BASE = 0x0103F698
INITIAL_DATA = ((0x6AD00C, 0x6AD8CC, 0x0103EEC0),)

SCENES = {"标题菜单": "menu", "直接进入关卡": "stage"}
ITEMS = {"无": "none", "加速（飞船）": "boost", "减速（敌人）": "slow", "奖命（+1）": "life"}
STAGES = tuple(range(1, 11))
DEFAULT_LIVES = 3
MAX_LIVES = 100
