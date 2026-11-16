# SGH-X458 的三款预置 Java 游戏

双击 `run.bat`，选择「BubbleSmile」「Fun2Link」或「Ultimate Golf Challenge」。窗口尺寸、音量、静音和倍速由启动器设置。游戏菜单沿用固件中的英文素材，画面为 128×160。

| 游戏 | 操作 |
|---|---|
| BubbleSmile | 方向键、WASD 或 2／4／6／8 移动，1／3 旋转相邻泡泡。Esc 或 # 保存当前棋盘并回到标题菜单。 |
| Fun2Link | 方向键、WASD 或 2／4／6／8 移动，5 放管段，* 加速计时和流动。关卡标题淡出后开始铺管。Esc 或 # 可在液体开始流动前暂停并回到菜单。 |
| Ultimate Golf Challenge | 1／3 调整击球方向，7／9 选杆，方向键移动地图，0 切换视角。进入挥杆视角后用 5 启动力度条、锁定力度，再按 5 击球。Esc 或 # 返回菜单。 |

方向键和 WASD 对应手机的导航键，Enter 和空格对应导航键中间的确认键，Esc 和 Backspace 对应 C 键。数字键、`*`、`#` 发送各自的键值。三款游戏均从菜单中的 `CONTINUE` 继续。BubbleSmile 关窗时也走原版的保存流程。Fun2Link 在同一窗口内可恢复暂停的棋盘，重新启动后按原版规则读取关卡记录。Ultimate Golf Challenge 沿用原版的击球及过洞存档时机。RMS 存档位于各游戏的 `.local/<游戏包名>/rms/` 目录，打包版对应 `%LOCALAPPDATA%/SGH-X458-Games/<游戏包名>/rms/`。

## 资源与运行层

`tools/java_games/extract.py` 从固件的文件表读取三份 JAR，校验 ZIP 条目，并把 Java 45.3 类中的指令、常量与异常表解析到各游戏的 `assets/runtime-data.bin`。包中也包含原版 PNG、关卡和球场图等数据。Java 指令由 `runtime/java_vm.py` 执行，`runtime/midp.py` 把按键、绘图、音频和 RMS 存档映射到桌面。定时器和线程按共享的游戏时钟调度。ROM 地址和原版资源清单见 [固件分析](firmware.md#预置-java-游戏)。

### 屏幕与裁剪

固件内置 Sun MIDP 1.0 参考实现。复刻版按 ROM 中的预加载类还原以下行为：

- 系统属性表（ROM `0x1365A8`）写有 `Display.HEIGHT=144`。`Canvas.getHeight()` 返回 144，`getWidth()` 是常量 128。高尔夫按 `getHeight()+18` 排布界面，因此底部 HUD 正好占满 160 行。
- 屏幕 Graphics 为 `new Graphics(128, Display.HEIGHT)`。`setClip` 把矩形钳制在 128×144 内，并且只会把 `clipped` 标志置真。每次重绘时，`reset` 把裁剪区设为未经钳制的脏矩形。
- `clipped` 为假时，`drawImage` 不裁剪，可以画到 LCD 的第 144–159 行；其他图元始终使用裁剪矩形。Fun2Link 先 `setClip(0,0,128,160)`，所以底部 HUD 图（`*SLOW`、计时条、`BACK#`）可见，随后的白色 `fillRect(0,151,128,9)` 被裁掉。这与实机照片一致。
- 文字使用手机自带的点阵字体。`tools/java_games/fonts.py` 从 ROM `0x50CCDC` 的固件字体表解码字形，写入 `runtime-data.bin` 的 `fonts.json`。SMALL 对应 SmallFont（粗体为 SmallFontB，6×8），MEDIUM 对应 Chinese 字体中拉丁字符使用的 17 行比例字形，LARGE 对应 SEC。锚点偏移与原生 `drawString`（`0x13D96C`）一致：SMALL 的 TOP 下移 2 行，BASELINE 和 BOTTOM 分别上移 8/9、14/17、19/24 行。x<0 的字符整字丢弃，超过 x=128 的字符不画。
- `Display.repaint` 先画进屏幕缓冲，再由 `refresh` 只把脏矩形送到 LCD。复刻版用 `Midlet.back` 和 `Midlet.surface` 分别对应这两层。

### 运行速度

三款游戏的动画大多由 `paint` 内再次调用 `repaint()` 连续推进，没有固定的帧间隔，实机上的速度取决于 KVM 解释字节码和绘图所花的 CPU 时间。复刻版按以下模型计时：

- 每条字节码耗时 3 µs（`java_vm.BYTECODE_US`），每个绘制像素耗时 4.4 µs（`midp.PIXEL_US`）。线程像 KVM 绿色线程一样按 1 ms 时间片轮转，CPU 忙时其他线程顺延，`Thread.sleep` 与绘制可以重叠。
- 按键和重绘由同一个 MIDP 事件线程依次处理，`serviceRepaints` 在调用线程内完成待处理的重绘。
- 参数按实机录像标定。BubbleSmile 开局的落下、消除共 11 次连续绘制，每次约 7k 条字节码、5 万像素，实机约 2.6 秒。空闲时计时条每 300 ms 减 1 格，与实机一致，整条约 27 秒；消除会给计时条加时。
- Fun2Link 替换管段后，爆炸线程每 60 ms 推进一帧，结束时清除 `isBoom` 再调用 `serviceRepaints`。实机一次局部重绘超过 60 ms，最后一帧绘制时爆炸已结束，所以光标框里显示下一节管段。复刻版按同样的时序得到相同画面。

### 按键、音效与定时器

- 按键表取自固件原生的 `getGameAction`（ROM `0x1313EC`）：只有导航键映射到上、下、左、右和确认，`GAME_A`–`GAME_D` 对应 7、9、`*`、`#`，其余数字键返回 0。BubbleSmile 的排行榜和玩法说明页只认确认键或 C 键退出，按数字 5 无效，与实机一致。
- `com.samsung.util.AudioClip` 按 ROM 中的类实现：每个音效有 `playing` 标志，播放中再次 `play()` 会被忽略，`stop()` 才清除标志并停止当前声音。高尔夫的 `select.mmf` 缺失时游戏会对上一个音效再调一次 `play()`，实机上不出声，复刻版同样不出声。`play` 的音量参数（BubbleSmile 和高尔夫为 1，Fun2Link 为 3）尚未换算，三款游戏按同一音量播放。
- `java.util.Timer` 区分固定频率和固定间隔：前者按上次应执行的时刻加周期，后者按上次实际开始的时刻加周期。
- `Image.createImage(宽, 高)` 新建的图像初始为白色。
- 长按按键时的 `keyRepeated` 事件没有模拟。Fun2Link 的 `keyRepeated` 会移动光标，实机长按是否连续移动尚未确认。

17 段原版 MMF 使用项目现有的 Yamaha MA-3 工具渲染成 WAV，单文件版打包为 OGG。高尔夫 JAR 引用的 `select.mmf` 在原包中缺失，保留原游戏对缺失资源的处理。

## 验证与重新提取

```powershell
.\.venv\Scripts\python.exe -B -m tools.java_games.verify
.\.venv\Scripts\python.exe -B -m tools.java_games.extract
```

验证脚本覆盖 BubbleSmile 的旋转、存档后重开时分数与棋盘一致，Fun2Link 的放管、暂停、续玩、失败及第 1 关结算，Ultimate Golf Challenge 的挥杆、落点及重开继续。Fun2Link 的过关用例预置了已连通的管线，随后执行原版的流动和过关流程。验证按游戏状态等待，不依赖固定延时。BubbleSmile 的棋盘由时钟播种，每次不同。计时模型只用一段录像标定，真机逐帧对照、完整通关和扬声器音色对照仍待验证。

重新渲染音效时，用 32 位 Windows Python 执行 `python -m tools.render_audio <ma3smwemu.dll> --assets src/sgh_x458/<游戏包名>/assets`。
