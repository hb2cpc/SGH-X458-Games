# Anycall SGH-X458 游戏复刻

双击根目录 `run.bat` 打开启动器，再选择《X-战机》《空间大战》或《我的宠物》。

## Windows 单文件版

把 `dist/SGH-X458-Games.exe` 复制到另一台 64 位 Windows 电脑即可双击运行。EXE 内置 Python、三款游戏和运行素材，设置与存档写入 `%LOCALAPPDATA%\SGH-X458-Games`。

在已安装项目依赖的 Windows x64 Python 3.12 环境中，可以用以下命令重新构建。

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --workpath .local\package-build SGH-X458-Games.spec
```

## 安装与启动选项

三个游戏共用根目录的 `.venv` 和 `src/sgh_x458/` 下的启动器与运行层，游戏代码和素材放在各自的子包。启动器可选窗口尺寸和音量。《X-战机》支持场景跳转、练习、无敌和倍速，《空间大战》支持选关、初始后备机、道具、无敌和倍速，《我的宠物》支持倍速。默认窗口 400×500，默认音量 50%，设置在启动游戏时保存至 `.local/launcher.json`。

从标题菜单开始的游戏会在关窗时保存进度。使用相同游戏设置重开后，在标题菜单按 `4` 或小键盘 `4` 继续，按 `1` 开始新游戏。两款战斗游戏的正式模式与练习模式分别保存。选择战斗进度、Boss 战或直接进入关卡时，每次都从选定的场景开局。

如果需要重新创建环境，在项目根目录使用 Python 3.12 运行以下命令。依赖定义在 `pyproject.toml`；`[tools]` 额外安装离线对照用的 Unicorn，只玩游戏可以省略。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[tools]"
```

安装后也可以不经 `run.bat` 直接启动：`python -m sgh_x458` 打开启动器，`python -m sgh_x458.x_fighter`、`python -m sgh_x458.spacewar`、`python -m sgh_x458.mypet` 直接进入游戏，参数见各游戏的 `--help`。`run.bat` 自己设置 `PYTHONPATH`，不安装也能运行。

三款游戏用 Python 实现游戏逻辑，读取已提取的画面和数据表，并播放从固件 SMAF 重新渲染的音频。`firmware/` 保存刷机镜像，`tools/` 保存离线工具和追踪数据。

## 目录结构

```text
pyproject.toml            依赖、入口命令与打包配置
run.bat                   双击启动器
SGH-X458-Games.spec       PyInstaller 单文件构建
src/sgh_x458/
  launcher.py             Tk 启动器（python -m sgh_x458）
  runtime/                三款游戏共用的固件调用、定时器、位图、整数运算、桌面适配和成绩编辑器
  x_fighter/ spacewar/ mypet/
    play.py               桌面入口（python -m sgh_x458.<game>）
    game.py               Game 类：接入共用运行层和本游戏的规则覆盖
    layout.py             资源路径、ROM 区间和 RAM 状态地址
    game_flow.py          lift 生成的固件静态翻译，勿手改
    assets/               runtime-data.bin、manifest.json、WAV 与原始 MMF
tools/
  firmware.py lift.py oracle.py assets.py render_audio.py   各游戏共用的离线工具
  x_fighter/ spacewar/ mypet/                               提取、追踪、ARM 对照和追踪数据
docs/                     各游戏的说明与逆向记录
firmware/                 原始刷机镜像
.local/                   本机存档、启动设置和按需生成的离线输出（不入库）
```

每款游戏从 `assets/runtime-data.bin` 读取画面和固件常量，从 `assets/audio/firmware_wav/` 播放音频。原始 MMF 保留供离线重渲染。《X-战机》额外有 `game_rules.py`（具名战斗规则）、`practice.py`（练习跳转）和 `audio_mix.py`（录音对照的音频适配）。

- [X-战机](docs/x_fighter.md)
- [空间大战](docs/spacewar.md)
- [我的宠物](docs/mypet.md)

## 固件与共用调度

- 机型为三星 Anycall SGH-X458，游戏画面为 128×160，帧缓冲为 RGB565。
- 固件为 `firmware/X458ZCEK1.s3`，大小 40,988,492 字节。SHA-256 为 `2e39ad4672c708498419aaca63843e500f6798f2d94171cd890b9ef86f1e9fad`。
- 文件为 Motorola S-Record，含 1 条 S0、853,927 条 S3 和 1 条 S7。S3 的 32 位大端字段给出装载地址，从 `0x00000000` 开始。解析后的 ROM 上界为 `0xD63DD8`，未覆盖的字节填 `0xFF`。S7 值为 `0xA0020000`。
- 用 [firmware.py](tools/firmware.py) 的 `load_rom()` 校验原始文件哈希、逐行长度和校验和，再按装载地址读取。本文的 ROM 地址指解析后的位置。多字节数据的端序以实际字段为准。注册表中的 Thumb 指针最低位为 1，记录和挂钩使用清掉最低位后的指令地址。区间均为左闭右开。
- 离线对照器把 RAM 映射到 `0x01000000–0x01400000`。逆向时同时检查 ROM 中的初始化数据和 RAM 目标地址，尤其是指针表、资源选择表和跨场景存档字段。

### 游戏注册表与服务地址

从 ROM `0x5995B0` 开始，每条记录为 28 字节。前两个字段是内部名和短名指针，`+0x08` 是回调指针，`+0x10` 和 `+0x14` 是宽高。三条记录的 `+0x18` 都是 `0x4C`，对应 76 字节的记录；三款游戏均已按此长度接入桌面存档，《我的宠物》的记录里是宠物状态与时间戳，不是排行榜。

| 索引 | 子包与固件名 | 注册记录 | Thumb 指针 | 回调地址 |
|---|---|---|---|---|
| 0 | `x_fighter` · `G58 AirShooting` | `0x5995B0` | `0x235A35` | `0x235A34` |
| 1 | `spacewar` · `G94 SpaceWar` | `0x5995CC` | `0x2379DD` | `0x2379DC` |
| 2 | `mypet` · `G133 MyPet` | `0x5995E8` | `0x238023` | `0x238022` |

共用调度器的调用层和各游戏回调的事件编号是两层接口。用离线对照器初始化显示后，可以调用 `game.call(0x20D7AD, 0, 10 * language + game_index)` 打开相应菜单。简体中文用 `language=1`，三款游戏依次传 10、11、12。`Session.open_menu()` 读取游戏类的 `game_index`。已观察到游戏回调的事件 0 绘制菜单标志、1 开始游戏、4 定时更新、5 处理游戏内按键、9 绘制帮助，具体参数和其余事件按游戏核实。《我的宠物》打开菜单时还先收到事件 11。

| 固件地址 | 用途 |
|---|---|
| `0x20D1F6` | 游戏显示初始化和前后缓冲 |
| `0x20D7AC` | 共用调度器。外部事件 0 打开菜单，1 定时回调，2 按键，3 退出 |
| `0x22B100`、`0x22B174` | 位图绘制和可镜像的位图绘制 |
| `0x22808E` | 提交 RGB565 帧 |
| `0x228174`、`0x2281F0` | 注册和停止游戏定时器。注册按 `(毫秒 * 13 + 59) // 60` 换算为刻度 |
| `0x2280D8`、`0x228134`、`0x22813E`、`0x228148` | 播放、停止、暂停和恢复音频 |
| `0x228224`、`0x2282C4` | 存档读取和写入服务 |

### 共用成绩录入

- 两款游戏共用的成绩录入在光标右移时会拼接 ROM `0x22BB54` 的空格字符串。`tools/x_fighter/lift.py` 与 `tools/spacewar/extract.py` 都显式打包了 `0x22BB50–0x22BB60`，重做离线提取时不可省略。
- 成绩录入是共用调度器的 UI：光标 `0x0103EFDC`、名字缓冲指针 `0x0103EFE8`、上限 10 字符、绘制入口 `0x22B5C6`。桌面版用 Python 的 `type_score_character()` 直接写 ASCII 并调用绘制例程刷新 RGB565 帧，绕过手机九宫格多击；`src/sgh_x458/runtime/score_editor.py` 提供两款游戏共用的实现，`runtime/keys.py` 处理桌面键盘映射。

## 复刻方法

1. 用注册表和共用调度器进入目标游戏，以已知的菜单、帮助和开场作为第一批可重复的探针。记录回调事件、定时器、绘图参数、音频地址与长度、RAM 读写和存档调用。每款游戏分别使用独立的探针存档。
2. 沿绘图和音频调用追溯资源指针与调色板，确认连续记录的起止和格式后再批量导出。用 ROM 地址、长度和哈希记录来源。画面与固件提交的 RGB565 帧对照。SMAF 原样保存，再离线渲染 WAV。真机录音用于比较音色和时序。
3. 从开场进入实际玩法，定位状态分发表、更新节拍和初始化数据。《我的宠物》已按此路径完成：追踪输入动作、状态变化、定时更新以及退出重进时的存档恢复，每条规则以 ROM 代码、追踪或实机测量确认后写入 Python。
4. 先验证正常操作路径，再验证边界和跨场景保存。对照时分别记录状态、帧缓冲、音频事件和存档字节。把桌面输入、显示与启动选项放在适配层，并注明与真机测量的边界。

## 固件对照验证

安装 `[tools]` 依赖后，在项目根目录运行以下命令。各游戏说明还列出了资源提取方法、对照范围和待实测项。

```powershell
.\.venv\Scripts\python.exe -B -m tools.x_fighter.verify_source --compare-rom --all-stages
.\.venv\Scripts\python.exe -B -m tools.spacewar.verify
.\.venv\Scripts\python.exe -B -m tools.mypet.verify
```
