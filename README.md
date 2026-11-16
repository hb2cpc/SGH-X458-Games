<p align="center"><img src="src/sgh_x458/resources/icon.png" width="128" alt="SGH-X458 游戏复刻图标"></p>

# SGH-X458 游戏复刻

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Platform Windows and Android](https://img.shields.io/badge/Platform-Windows%20%7C%20Android-0078D6)
![License MIT](https://img.shields.io/badge/License-MIT-green)

在 Windows 和 Android 上重玩三星 Anycall SGH-X458 固件中的六款游戏，包括三款原生游戏《X-战机》《空间大战》《我的宠物》，以及三款预置 Java 游戏 BubbleSmile、Fun2Link 和 Ultimate Golf Challenge。

## 游戏截图

| X-战机 | 第 2 关战斗 | 第 1 关 Boss |
|:---:|:---:|:---:|
| ![X-战机 标题菜单](docs/images/x_fighter-1-menu.png) | ![X-战机 第 2 关战斗](docs/images/x_fighter-2-battle.png) | ![X-战机 第 1 关 Boss](docs/images/x_fighter-3-boss.png) |

| 空间大战 | 第 1 关 | 第 5 关 |
|:---:|:---:|:---:|
| ![空间大战 标题菜单](docs/images/spacewar-1-menu.png) | ![空间大战 第 1 关](docs/images/spacewar-2-play.png) | ![空间大战 第 5 关](docs/images/spacewar-3-stage5.png) |

| 我的宠物 | 宠物房间 | 带宠物看医生 |
|:---:|:---:|:---:|
| ![我的宠物 标题菜单](docs/images/mypet-1-menu.png) | ![我的宠物 宠物房间](docs/images/mypet-2-room.png) | ![我的宠物 看医生](docs/images/mypet-3-doctor.png) |

| BubbleSmile | Fun2Link | Ultimate Golf Challenge |
|:---:|:---:|:---:|
| ![BubbleSmile 泡泡棋盘](docs/images/bubble_smile-play.png) | ![Fun2Link 第 1 关](docs/images/fun2link-play.png) | ![Ultimate Golf Challenge 挥杆视角](docs/images/ultimate_golf-play.png) |

## Android

支持装有 Android 7.0 或更高版本的 64 位 ARM 手机，也可在 x86_64 模拟器运行。APK 内含六款游戏和音频，可离线游玩。游戏库点游戏名称进入，点「⋯」调整倍速或战斗选项。游戏内用虚拟方向键、OK、C 和数字键操作，点「玩法」查看当前游戏的按键说明。

《X-战机》战斗中，方向键、导弹和核弹按下后立即处理并重绘，地图、敌机和常规射击仍按原有战斗定时器推进。

《X-战机》《空间大战》回游戏库或切到后台时保存可续玩的进度，回到游戏标题菜单按 4 继续。《我的宠物》按原版存档继续。BubbleSmile 回游戏库时保存棋盘。三款 Java 游戏在标题菜单选择 `CONTINUE` 读取存档，Fun2Link 和高尔夫沿用各自原版的保存时机。

在 Windows 上构建需要 JDK 17 至 24（Gradle 8.14 不支持 JDK 25）、Android SDK Platform 36、Python 3.12 和支持 Vorbis 的 ffmpeg。装有 Android NDK 时，构建会把用不到的 OpenSSL 和 SQLite 换成空库，安装包再小约 3 MB。Gradle 增量打包会在 APK 里留下空洞，发布前加 `--rerun-tasks` 或先 `clean` 才能得到最小的包。让 Gradle 能通过 `ANDROID_HOME` 找到 SDK，或在 `android/local.properties` 配置 `sdk.dir`。用 Android Studio 打开 `android/`，也可从项目根目录运行：

```powershell
cd android
.\gradlew.bat :app:assembleDebug
```

在 `android/app/build/outputs/apk/` 下生成 `arm64/debug/app-arm64-debug.apk`（手机）和 `emulator/debug/app-emulator-debug.apk`（x86_64 模拟器）。如果 PATH 中的 `python` 没有指向 Python 3.12，构建时可用 `-PgamePython=...` 指定解释器。

## Windows 部署与运行

需要 Windows 10/11 和 [Python 3.12](https://www.python.org/downloads/)。以下命令在 PowerShell 中运行。

**1. 获取代码**

```powershell
git clone https://github.com/hb2cpc/SGH-X458-Games.git
cd SGH-X458-Games
```

**2. 创建虚拟环境**

```powershell
python -m venv .venv
```

**3. 安装依赖**

依赖写在 `pyproject.toml` 里（作用相当于 `requirements.txt`），运行游戏只需要 `pygame-ce`：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

**4. 运行**

双击 `run.bat` 打开启动器，或在命令行运行：

```powershell
.\.venv\Scripts\python.exe -m sgh_x458             # 启动器
.\.venv\Scripts\python.exe -m sgh_x458.x_fighter   # 直接进入 X-战机，加 --help 查看参数
```

可把 `x_fighter` 换成 `spacewar`、`mypet`、`bubble_smile`、`fun2link` 或 `ultimate_golf`。存档和设置保存在项目根目录的 `.local/` 下。三款 Java 游戏的按键和续玩规则见 [Java 游戏说明](docs/java_games.md)。

**5. 打包成单文件 EXE（可选）**

需要先安装 [ffmpeg](https://ffmpeg.org/)（用于把音频压缩成 OGG）并加入 PATH：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --workpath .local\package-build SGH-X458-Games.spec
```

生成的 `dist\SGH-X458-Games.exe` 约 15 MB，复制到 Windows 10/11 电脑上双击即可运行。存档写在 `%LOCALAPPDATA%\SGH-X458-Games`。

## 逆向流程

原生游戏沿用以下流程。

1. 用 Unicorn 运行固件里的游戏代码，记录执行过的代码和读过的数据。
2. 把这些 ARM Thumb 指令逐条翻译成 Python（`game_flow.py`），用到的图像、音频和数据表一并提取出来。
3. 用 Python 实现游戏依赖的手机系统服务：画面、声音、定时器、存档。
4. 让翻译版和原版代码执行同样的操作，逐帧比较画面、状态和存档，确认一致。

三款 Java 游戏从固件提取 JAR，离线解析其中的类和资源，由共享的 Python 运行层执行原版指令。Android 通过 Chaquopy 运行同一套游戏逻辑，使用 Android Canvas 绘制 Java 游戏，用 MediaPlayer 播放音频。运行时所需数据均已打包。固件格式、ROM 地址和原版资源见 [固件分析](docs/firmware.md)。

## 与原版游戏的不同

- 新增启动器、窗口缩放、倍速，以及两款战斗游戏的跳关、无敌、初始装备等练习选项（成绩记入单独的练习排行榜）。
- 两款战斗游戏关窗时自动保存进度，下次在菜单按 4 继续；中途更改启动器设置也能继续。
- 键盘操作：方向键／WASD 移动，录入成绩时直接打字，不用九宫格。
- X-战机的部分音效按真机录音调整了音量和低频。
- 声音由 Yamaha MA-3 软件引擎渲染，与真机扬声器的音色会有差异。

## 许可与声明

代码以 [MIT 许可证](LICENSE) 发布。固件、游戏素材和截图版权归三星电子及原游戏开发者所有，不在 MIT 许可范围内。本项目仅用于技术研究和老游戏保存，与三星电子无关。

## 致谢

[Unicorn Engine](https://www.unicorn-engine.org/)、[pygame-ce](https://pyga.me/)、[libsmaf](https://github.com/denjhang/libsmaf)（Yamaha MA-3 渲染器）、[PyInstaller](https://pyinstaller.org/)、[Chaquopy](https://chaquo.com/chaquopy/)。
