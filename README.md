# SGH-X458 游戏复刻

把三星 Anycall SGH-X458 手机固件里的三款内置游戏，复刻成可以在电脑上运行的 Python 程序：

- **X-战机**：纵版射击，三个关卡，各有 Boss。
- **空间大战**：圈地揭图，共十关。
- **我的宠物**：电子宠物，状态随真实时间变化。

本项目不是模拟器，不运行手机的 ARM 代码。游戏逻辑由工具从固件的 Thumb 机器码逐条翻译成 Python；画面和音频直接从固件提取。复刻结果用 [Unicorn](https://www.unicorn-engine.org/) 运行原版 ARM 代码逐帧对照：在测试覆盖的场景中，画面、游戏状态、定时器、音频请求和存档字节都与原版一致。

| 游戏 | 固件内部名 | 说明 |
|---|---|---|
| X-战机 | G58 AirShooting | [docs/x_fighter.md](docs/x_fighter.md) |
| 空间大战 | G94 SpaceWar | [docs/spacewar.md](docs/spacewar.md) |
| 我的宠物 | G133 MyPet | [docs/mypet.md](docs/mypet.md) |

## 快速开始

需要 Windows 和 Python 3.12。项目主要在 Windows 上开发和测试。克隆仓库后，在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

装好后双击 `run.bat` 打开启动器，选择游戏、窗口尺寸和音量，再点「启动游戏」。

也可以在命令行运行：

```powershell
.\.venv\Scripts\python.exe -m sgh_x458             # 启动器
.\.venv\Scripts\python.exe -m sgh_x458.x_fighter   # 直接进入 X-战机
.\.venv\Scripts\python.exe -m sgh_x458.spacewar    # 直接进入空间大战
.\.venv\Scripts\python.exe -m sgh_x458.mypet       # 直接进入我的宠物
```

每个游戏都支持 `--help` 查看参数，例如 `--size 300x375` 设置窗口尺寸，`--volume 30` 设置音量，`--mute` 静音，`--speed 1.5` 设置倍速，`--language 0` 切换英文（`1` 简体中文，为默认值；`2` 繁体中文）。

## 启动器功能

- **共用设置**：窗口尺寸有 128×160（原始分辨率）、200×250、300×375、400×500 四档，最近邻缩放；可调音量或静音。
- **X-战机**：可从标题菜单开始，或直接跳到某一关的指定战斗进度或 Boss 战，并选择战机。可开启无敌，设置开局武器强化、初始护盾和炸弹数量（0–10），以及 0.5×–2× 倍速。
- **空间大战**：可直接进入第 1–10 关，设置初始后备机（0–100）、开局道具、无敌和倍速。
- **我的宠物**：倍速。

两款战斗游戏只要改动过上述任一选项（倍速也算），成绩就记入单独的练习排行榜，不影响正式排行榜。

## 操作

| 场景 | X-战机 | 空间大战 | 我的宠物 |
|---|---|---|---|
| 标题菜单 | Enter／1 开始，2 最高分，3 帮助，4 继续 | 同左 | Enter／1 开始，3 帮助，4 继续存档 |
| 移动 | 方向键／WASD | 方向键／WASD，点按一次后持续移动 | ←／→ 选图标 |
| 动作 | 普通子弹自动发射；Z／空格 导弹，X 核弹 | 空格／5 停止移动 | Enter／空格 确认 |
| 暂停与返回 | Esc／Backspace | Esc 暂停，Enter／4 恢复 | Esc 返回 |
| 成绩录入 | 直接键入字母、数字、空格；Backspace 删除，Enter 保存 | 同左 | — |

手机原有的数字键操作同样可用，主键盘和小键盘都行。各游戏的完整按键说明见启动器下方或 `docs/` 中的文档。

## 存档

- **两款战斗游戏**：从标题菜单开始的游戏，关闭窗口时自动保存进度；下次用相同设置打开后，在标题菜单按 4 继续。
- **我的宠物**：使用固件自己的存档。
- **存档位置**：从源码运行时在项目根目录的 `.local/`；单文件 EXE 写在 `%LOCALAPPDATA%\SGH-X458-Games`。

## 工作原理

```text
firmware/X458ZCEK1.s3 ──► tools/<game>/trace.json   用 Unicorn 运行原版代码，记录执行过的代码块与数据读取
                      ──► lift／extract              把 Thumb 指令翻译成 game_flow.py，打包所需的 ROM 数据，
                                                     导出图像清单和原始 SMAF 音频
                      ──► tools/render_audio         用 Yamaha MA-3 引擎把 SMAF 渲染成 WAV

src/sgh_x458/runtime  ◄── game_flow.py + assets/  用 Python 实现手机系统服务（定时器、绘图、音频、存档），
        │                                         再交给 pygame 显示
        └──► tools/<game>/verify                  与 Unicorn 运行的原版代码逐帧对照
```

- **翻译代码**：`game_flow.py` 保留了固件地址、寄存器和内存布局，便于对照反汇编逐段核对，请勿手改，需要时用 `tools/` 重新生成。
- **玩法改动**：通过 `game.py` 中按固件地址覆盖例程实现。X-战机的战斗规则另在 `game_rules.py` 里用具名函数重写。
- **出错时直接报错**：运行中如果遇到未翻译的代码或未打包的数据，程序会报错退出，不会悄悄算错。

## 与原版的差异

以下是有意为之的桌面适配，不属于复刻偏差：

- **成绩录入**：直接键盘输入，不再用手机九宫格多次按键选字。
- **标题菜单配色**：数字按钮的颜色在桌面上重新着色。
- **X-战机音效**：5 段音效按真机录音削减低频并降低音量；激光连续坠机的音效间隔按真机录音设为 382 毫秒。
- **X-战机操作**：长按移动时，导弹和核弹指令会排队，每次战斗更新执行一个。
- **额外功能**：关窗保存进度、倍速、无敌、跳关、练习排行榜，都是原版没有的功能。
- **窗口卡顿保护**：每帧最多推进 100 毫秒，窗口卡住（例如拖动窗口）后不会一次补跑大量游戏更新。
- **声音与显示**：声音由 MA-3 软件引擎渲染，不是真机芯片的原声；颜色按 RGB565 线性换算，未模拟手机 LCD 的显示特性。

尚待真机实测的项目：屏幕颜色、扬声器音色、空间大战十关自然通关，以及我的宠物长期养成的结果。

## 项目结构

```text
src/sgh_x458/
  launcher.py              Tk 启动器
  runtime/                 三款游戏共用的系统服务、位图绘制、整数运算、桌面适配和成绩录入
  x_fighter/ spacewar/ mypet/
    play.py                桌面入口
    game.py                游戏类，在这里覆盖固件例程
    layout.py              资源路径、ROM 区间、RAM 地址
    game_flow.py           从固件翻译的代码（生成物）
    assets/                runtime-data.bin、manifest.json、WAV 和原始 MMF
tools/                     离线追踪、翻译、资源导出、音频渲染和固件对照
docs/                      各游戏说明、固件与逆向记录
firmware/                  原始刷机镜像 X458ZCEK1.s3
```

## 开发

### 安装开发依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[tools]"
```

`[tools]` 会安装 Unicorn，用于运行离线对照。

### 固件对照验证

```powershell
.\.venv\Scripts\python.exe -B -m tools.x_fighter.verify_source --compare-rom --all-stages
.\.venv\Scripts\python.exe -B -m tools.x_fighter.verify --all-stages
.\.venv\Scripts\python.exe -B -m tools.spacewar.verify
.\.venv\Scripts\python.exe -B -m tools.mypet.verify
```

修改 `runtime/`、`game.py` 或 `game_rules.py` 后，请重新运行对应的验证。`tools.x_fighter.verify --all-stages` 要在原版代码里打完三个 Boss，约需 20 分钟；其余每条在 2 分钟以内。

### 重新生成翻译代码和素材

```powershell
.\.venv\Scripts\python.exe -B -m tools.x_fighter.lift
.\.venv\Scripts\python.exe -B -m tools.spacewar.extract
.\.venv\Scripts\python.exe -B -m tools.mypet.extract
```

这些命令会根据 `tools/<game>/trace.json` 和固件重新生成 `game_flow.py` 和 `assets/`。在现有追踪数据下，重新生成的结果与仓库中的文件逐字节相同。重新渲染 WAV 需要 32 位 Windows Python 和 MA-3 引擎 DLL，见 [docs/x_fighter.md](docs/x_fighter.md)。

### 构建 Windows 单文件 EXE

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --workpath .local\package-build SGH-X458-Games.spec
```

生成的 `dist/SGH-X458-Games.exe` 内含 Python、三款游戏和全部素材，复制到其他 64 位 Windows 电脑上可以直接运行。

### 深入资料

- [固件与共用调度](docs/firmware.md)：固件格式、游戏注册表、系统服务地址和逆向方法。
- [X-战机](docs/x_fighter.md)、[空间大战](docs/spacewar.md)、[我的宠物](docs/mypet.md)：各游戏的资源区间、逆向记录和验证范围。

## 许可与声明

本项目的原创代码和文档以 [MIT 许可证](LICENSE) 发布。

`firmware/` 中的三星 SGH-X458 固件，以及从中提取或翻译出的游戏图像、音频、文字和程序逻辑（包括 `src/sgh_x458/*/assets/` 和生成的 `game_flow.py`），版权归三星电子及原游戏开发者所有，不在 MIT 许可范围内。本项目仅用于技术研究和老游戏保存，与三星电子无关，也未获其授权。如果权利人认为本项目有不妥之处，请通过 Issue 联系，我们会及时处理。

## 致谢

- [Unicorn Engine](https://www.unicorn-engine.org/)：运行原版 ARM 代码做对照。
- [pygame-ce](https://pyga.me/)：显示与音频。
- [libsmaf](https://github.com/denjhang/libsmaf) 收录的 Yamaha MA-3 渲染器：离线把 SMAF 渲染成 WAV。
- [PyInstaller](https://pyinstaller.org/)：打包单文件 EXE。
