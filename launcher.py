"""Shared Windows launcher for the three SGH-X458 games."""

import json
import os
import subprocess
import sys
import tkinter as tk
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from tempfile import NamedTemporaryFile
from tkinter import font, messagebox, ttk

from handset.desktop import (
    DEFAULT_SIZE, DEFAULT_SPEED, DEFAULT_VOLUME, SPEED_QUARTERS, WINDOW_SIZES, data_directory,
)
from SpaceWar.layout import DEFAULT_LIVES, ITEMS, MAX_LIVES, SCENES as SPACEWAR_SCENES, STAGES as SPACEWAR_STAGES


ROOT = Path(__file__).resolve().parent
FROZEN = getattr(sys, "frozen", False)
SETTINGS_PATH = data_directory(ROOT) / "launcher.json"
GAMES = (
    ("X-Fighter", "X-战机"),
    ("SpaceWar", "空间大战"),
    ("MyPet", "我的宠物"),
)
GAME_DIRS = {label: directory for directory, label in GAMES}
KEY_GUIDES = {
    "X-Fighter": (
        ("标题菜单", "Enter／1 开始，2 最高分，3 帮助，4 继续"),
        ("封面与选机", "Enter 进入选机，↑／↓ 或 W／S 选择，Enter 确认"),
        ("战斗移动", "方向键／WASD，或 1 上、4 左、5 右、7 下"),
        ("武器", "J 普通射击，Z／空格／6 发射导弹，X／9 投放核弹"),
        ("暂停与返回", "Esc／Backspace"),
        ("成绩录入", "字母／数字／空格输入，←／→ 移动光标\nBackspace 删除，Enter 保存"),
    ),
    "SpaceWar": (
        ("标题菜单", "Enter／1 开始，2 最高分，3 帮助，4 继续"),
        ("开场与过关", "Enter／空格／5 确认"),
        ("移动与停止", "方向键／WASD／2、4、6、8 移动，5／空格停止"),
        ("暂停与恢复", "Esc／Backspace 暂停，Enter／4 恢复"),
        ("续关提示", "7 续关，9 结束"),
        ("成绩录入", "字母／数字／空格输入，方向键移动光标\nBackspace 删除，Enter 保存"),
    ),
    "MyPet": (
        ("标题菜单", "Enter／1 开始，3 帮助，4 继续存档"),
        ("帮助翻页", "←／→ 或 4／6 翻页，Esc 返回"),
        ("开场动画", "Enter／空格进入宠物房间"),
        ("宠物房间", "←／→、A／D 或 4／6 选图标，Enter／空格确认"),
        ("返回与退出", "Esc／Backspace 返回，标题菜单按 Esc 退出"),
    ),
}
X_FIGHTER = import_module("X-Fighter.layout")
SCENES = {"标题菜单": "menu", "战斗进度": "battle", "Boss 战": "boss"}
AIRCRAFT = {"速度+": "1", "攻击+": "2", "防御+": "3"}
LEGACY_AIRCRAFT = {number: label for label, number in AIRCRAFT.items()}
SIZES = {f"{width} × {height}": key for key, (width, height) in WINDOW_SIZES.items()}
DEFAULTS = {
    "game": "X-战机", "scene": "标题菜单", "stage": "1", "aircraft": "速度+",
    "progress": "0.0", "invincible": False, "weapon": "默认",
    "shield": "关闭", "bombs": str(X_FIGHTER.DEFAULT_BOMBS), "speed": DEFAULT_SPEED,
    "spacewar_scene": "标题菜单", "spacewar_stage": "1", "spacewar_lives": str(DEFAULT_LIVES),
    "spacewar_item": "无", "spacewar_speed": DEFAULT_SPEED, "spacewar_invincible": False,
    "mypet_speed": DEFAULT_SPEED,
    "size": next(label for label, key in SIZES.items() if key == DEFAULT_SIZE),
    "mute": False, "volume": str(DEFAULT_VOLUME),
}
CHOICES = {
    "game": GAME_DIRS, "scene": SCENES, "stage": ("1", "2", "3"),
    "aircraft": AIRCRAFT, "weapon": ("默认", "强化"),
    "shield": ("关闭", "开启"), "speed": SPEED_QUARTERS, "size": SIZES,
    "spacewar_scene": SPACEWAR_SCENES, "spacewar_stage": tuple(map(str, SPACEWAR_STAGES)),
    "spacewar_item": ITEMS, "spacewar_speed": SPEED_QUARTERS,
    "mypet_speed": SPEED_QUARTERS,
}


def load_options():
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULTS.copy()
    if not isinstance(saved, dict):
        return DEFAULTS.copy()
    options = DEFAULTS.copy()
    for name, default in DEFAULTS.items():
        value = saved.get(name)
        if name == "aircraft" and isinstance(value, str):
            value = LEGACY_AIRCRAFT.get(value, value)
        if name == "shield" and value == "充满":
            value = "开启"
        if name == "bombs" and isinstance(value, str):
            try:
                value = number(value, "炸弹数量", X_FIGHTER.MAX_BOMBS)
            except ValueError:
                continue
        if type(value) is type(default) and (name not in CHOICES or value in CHOICES[name]):
            options[name] = value
    return options


def save_options(options):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = NamedTemporaryFile("w", encoding="utf-8", dir=SETTINGS_PATH.parent, delete=False)
    path = Path(temp.name)
    try:
        with temp:
            json.dump(options, temp, ensure_ascii=False, indent=2)
        path.replace(SETTINGS_PATH)
    finally:
        path.unlink(missing_ok=True)


def number(value, label, limit, convert=int):
    try:
        result = convert(value)
    except ValueError:
        raise ValueError(f"{label}请输入 0–{limit} 之间的数值。") from None
    if not 0 <= result <= limit:
        raise ValueError(f"{label}请输入 0–{limit} 之间的数值。")
    return str(result)


class Launcher:
    def __init__(self, window):
        self.window = window
        self.process = None
        window.title("Anycall SGH-X458 游戏启动器")
        window.resizable(False, False)
        self.options = {
            name: (tk.BooleanVar if isinstance(value, bool) else tk.StringVar)(window, value=value)
            for name, value in load_options().items()
        }
        family = font.nametofont("TkDefaultFont").actual("family")
        if "Microsoft YaHei UI" in font.families(window):
            family = "Microsoft YaHei UI"
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name).configure(family=family, size=10)
        window.option_add("*TCombobox*Listbox.font", "TkDefaultFont")
        style = ttk.Style(window)
        style.configure("Launch.TButton", font=(family, 11, "bold"), padding=(20, 9))

        panel = ttk.Frame(window, padding=(22, 18))
        panel.grid(sticky="nsew")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        panel.columnconfigure((0, 1), weight=1, uniform="options")
        panel.rowconfigure(1, weight=1)
        self.heading = ttk.Label(panel, font=(family, 24, "bold"))
        self.heading.grid(row=0, column=0, sticky="w")
        game = ttk.Combobox(panel, textvariable=self.options["game"], values=tuple(GAME_DIRS),
                            width=15, state="readonly")
        game.grid(row=0, column=1, sticky="e")
        game.bind("<<ComboboxSelected>>", self.refresh)
        self.x_panels = self.game_panels(panel)
        scene_box, feature_box = self.x_panels
        self.scene = self.field(scene_box, 0, "进入场景", "scene")
        self.scene.bind("<<ComboboxSelected>>", self.refresh)
        self.stage = self.field(scene_box, 1, "关卡", "stage")
        self.progress = self.field(scene_box, 2, "进度 %", "progress", spin=(0, 100, 0.1))
        self.aircraft = self.field(scene_box, 3, "战机", "aircraft")
        self.invincible = ttk.Checkbutton(feature_box, text="无敌", variable=self.options["invincible"])
        self.invincible.grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
        self.weapon = self.field(feature_box, 1, "武器等级", "weapon")
        self.shield = self.field(feature_box, 2, "初始护盾", "shield")
        self.bombs = self.field(feature_box, 3, "炸弹数量", "bombs", spin=(0, X_FIGHTER.MAX_BOMBS, 1))
        self.speed = self.field(feature_box, 4, "游戏倍速", "speed")

        self.spacewar_panels = self.game_panels(panel)
        scene_box, feature_box = self.spacewar_panels
        self.field(scene_box, 0, "进入场景", "spacewar_scene")
        self.field(scene_box, 1, "起始关卡", "spacewar_stage")
        self.spacewar_invincible = ttk.Checkbutton(
            feature_box, text="无敌", variable=self.options["spacewar_invincible"])
        self.spacewar_invincible.grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
        self.field(feature_box, 1, "初始后备机", "spacewar_lives", spin=(0, MAX_LIVES, 1))
        self.field(feature_box, 2, "初始道具", "spacewar_item")
        self.field(feature_box, 3, "游戏倍速", "spacewar_speed")

        mypet_box = ttk.LabelFrame(panel, text="游戏设置", padding=12)
        mypet_box.grid(row=1, column=0, columnspan=2, sticky="new", pady=(14, 0))
        mypet_box.columnconfigure(1, weight=1)
        self.mypet_panels = (mypet_box,)
        self.mypet_speed = self.field(mypet_box, 0, "游戏倍速", "mypet_speed")

        media = ttk.LabelFrame(panel, text="画面与声音", padding=12)
        media.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        media.columnconfigure(1, weight=1)
        self.field(media, 0, "窗口尺寸", "size")
        ttk.Checkbutton(media, text="静音", variable=self.options["mute"], command=self.refresh).grid(
            row=0, column=2, sticky="w", padx=(22, 12))
        self.volume = self.field(media, 0, "音量 %", "volume", spin=(0, 100, 1), column=3, width=6)

        controls = ttk.LabelFrame(panel, text="按键说明", padding=12)
        controls.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        controls.columnconfigure(0, weight=1)
        self.key_panels = {}
        for directory, rows in KEY_GUIDES.items():
            guide = ttk.Frame(controls)
            # Stack the guides so the largest one determines the frame size.
            guide.grid(row=0, column=0, sticky="nsew")
            self.key_panels[directory] = guide
            for row, (context, keys) in enumerate(rows):
                ttk.Label(guide, text=context).grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=2)
                ttk.Label(guide, text=keys, justify="left").grid(row=row, column=1, sticky="nw", pady=2)

        self.status = ttk.Label(panel, foreground="#526579")
        self.status.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(panel, text="恢复默认", command=self.restore_defaults).grid(
            row=5, column=0, sticky="w", pady=(14, 0))
        self.start = ttk.Button(panel, text="启动游戏", style="Launch.TButton", command=self.launch)
        self.start.grid(row=5, column=1, sticky="e", pady=(14, 0))
        window.bind("<Return>", lambda _: self.start.invoke())
        # Measure while all game panels still share the same grid row.
        window.update_idletasks()
        window.geometry(f"{window.winfo_reqwidth()}x{window.winfo_reqheight()}")
        self.refresh()

    @staticmethod
    def game_panels(parent):
        scene = ttk.LabelFrame(parent, text="启动场景", padding=12)
        features = ttk.LabelFrame(parent, text="游戏功能", padding=12)
        scene.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(14, 0))
        features.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(14, 0))
        for frame in (scene, features):
            frame.columnconfigure(1, weight=1)
        return scene, features

    def field(self, parent, row, label, name, *, spin=None, column=0, width=16):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 8), pady=4)
        args = {"textvariable": self.options[name], "width": width}
        if spin:
            first, last, step = spin
            widget = ttk.Spinbox(parent, from_=first, to=last, increment=step, **args)
        elif name in CHOICES:
            widget = ttk.Combobox(parent, values=tuple(CHOICES[name]), state="readonly", **args)
        else:
            widget = ttk.Entry(parent, **args)
        widget.grid(row=row, column=column + 1, sticky="ew", pady=4)
        return widget

    def game_entry(self):
        return ROOT / GAME_DIRS[self.options["game"].get()] / "play.py"

    def refresh(self, _event=None):
        entry = self.game_entry()
        x_fighter = entry.parent.name == "X-Fighter"
        spacewar = entry.parent.name == "SpaceWar"
        mypet = entry.parent.name == "MyPet"
        for enabled, group in ((x_fighter, self.x_panels),
                               (spacewar, self.spacewar_panels),
                               (mypet, self.mypet_panels)):
            for frame in group:
                frame.grid() if enabled else frame.grid_remove()
        self.key_panels[entry.parent.name].tkraise()
        self.heading.configure(text=self.options["game"].get())
        scene = SCENES[self.options["scene"].get()]
        self.scene.configure(state="readonly" if x_fighter else "disabled")
        self.stage.configure(state="readonly" if x_fighter and scene != "menu" else "disabled")
        self.aircraft.configure(state="readonly" if x_fighter and scene != "menu" else "disabled")
        self.progress.configure(state="normal" if x_fighter and scene == "battle" else "disabled")
        self.weapon.configure(state="readonly" if x_fighter else "disabled")
        self.shield.configure(state="readonly" if x_fighter else "disabled")
        self.speed.configure(state="readonly" if x_fighter else "disabled")
        self.bombs.configure(state="readonly" if x_fighter else "disabled")
        self.invincible.configure(state="normal" if x_fighter else "disabled")
        self.spacewar_invincible.configure(state="normal" if spacewar else "disabled")
        self.mypet_speed.configure(state="readonly" if mypet else "disabled")
        self.volume.configure(state="disabled" if self.options["mute"].get() else "normal")

        status = ""
        if FROZEN:
            entry_available = find_spec(f"{entry.parent.name}.play") is not None
            flow_available = find_spec(f"{entry.parent.name}.game_flow") is not None
        else:
            entry_available = entry.is_file()
            flow_available = (entry.parent / "game_flow.py").is_file()
        if not entry_available:
            status = "源码移植尚未开放"
        elif not flow_available or not all(
            (entry.parent / name).is_file() for name in ("assets/manifest.json", "assets/runtime-data.bin")
        ):
            status = "缺少游戏逻辑或固件数据"
        elif find_spec("pygame") is None:
            status = "请安装根目录 requirements.txt 中的依赖"
        running = self.process is not None
        self.start.configure(state="normal" if not status and not running else "disabled")
        self.status.configure(text=status)

    def restore_defaults(self):
        selected = self.options["game"].get()
        for name, value in DEFAULTS.items():
            self.options[name].set(value)
        self.options["game"].set(selected)
        self.refresh()

    def arguments(self, entry, options):
        args = ["--size", SIZES[options["size"]]]
        if entry.parent.name not in GAME_DIRS.values():
            return args
        volume = "0" if options["mute"] else number(options["volume"], "音量", 100)
        args += ["--volume", volume]
        if entry.parent.name == "MyPet":
            args += ["--speed", options["mypet_speed"]]
            if options["mute"]:
                args.append("--mute")
            return args
        if entry.parent.name == "SpaceWar":
            args += [
                "--scene", SPACEWAR_SCENES[options["spacewar_scene"]],
                "--stage", options["spacewar_stage"],
                "--lives", number(options["spacewar_lives"], "初始后备机", MAX_LIVES),
                "--start-item", ITEMS[options["spacewar_item"]],
                "--speed", options["spacewar_speed"],
            ]
            if options["spacewar_invincible"]:
                args.append("--invincible")
            return args
        scene = SCENES[options["scene"]]
        args += ["--scene", "battle" if scene == "boss" else scene, "--stage", options["stage"],
                 "--aircraft", AIRCRAFT[options["aircraft"]],
                 "--speed", options["speed"]]
        if scene == "boss":
            args += ["--progress", "100"]
        elif scene == "battle":
            args += ["--progress", number(options["progress"], "进度", 100, float)]
        args += ["--bombs", number(options["bombs"], "炸弹数量", X_FIGHTER.MAX_BOMBS)]
        if options["shield"] == "开启":
            args += ["--shield", "full"]
        elif scene != "menu":
            args += ["--shield", "off"]
        for enabled, flag in (
            (options["invincible"], "--invincible"),
            (options["weapon"] == "强化", "--upgraded"),
            (options["mute"], "--mute"),
        ):
            if enabled:
                args.append(flag)
        return args

    def launch(self):
        entry = self.game_entry()
        if self.start.instate(["disabled"]):
            return
        options = {name: variable.get() for name, variable in self.options.items()}
        try:
            args = self.arguments(entry, options)
            save_options(options)
            if FROZEN:
                # Give the game its own extraction directory so it survives launcher shutdown.
                env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
                self.process = subprocess.Popen([sys.executable, "--game", entry.parent.name, *args], env=env)
            else:
                self.process = subprocess.Popen([sys.executable, "-B", str(entry), *args], cwd=ROOT)
        except (OSError, ValueError) as error:
            messagebox.showerror("启动失败", str(error), parent=self.window)
            return
        self.refresh()
        self.window.after(250, self.check_game)

    def check_game(self):
        code = self.process.poll()
        if code is None:
            self.window.after(250, self.check_game)
            return
        self.process = None
        self.refresh()
        if code:
            messagebox.showerror("游戏异常退出", f"退出码 {code}。", parent=self.window)


def main():
    if sys.platform == "win32":
        from ctypes import windll

        # Let Tk 8.6 draw at the system DPI instead of stretching a 96-DPI window.
        windll.user32.SetProcessDPIAware()
    window = tk.Tk()
    window.withdraw()
    Launcher(window)
    window.deiconify()
    window.mainloop()


if __name__ == "__main__":
    if FROZEN and len(sys.argv) >= 3 and sys.argv[1] == "--game":
        game = sys.argv[2]
        if game not in GAME_DIRS.values():
            raise ValueError(f"Unknown game: {game}")
        del sys.argv[1:3]
        import_module(f"{game}.play").main()
    else:
        main()
