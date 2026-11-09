# 我的宠物 · SGH-X458 源码版

双击项目根目录 `run.bat`，在启动器中选择「我的宠物」。默认简体中文，内部画面为 128×160 RGB565。窗口默认 400×500，支持启动器的尺寸、音量、静音和 0.5×–2× 倍速。

## 操作

| 场景 | 操作 |
|---|---|
| 标题菜单 | Enter 或 1 开始新游戏，3 查看帮助，4 继续存档；Esc 关闭窗口 |
| 帮助 | 每 3 秒自动翻页，←／→ 或 4／6 手动翻页；Esc 返回菜单，翻页后 Enter 也可返回 |
| 开场动画 | Enter 或空格确认进入宠物房间 |
| 宠物房间 | ←／→ 或 4／6 在底部六个图标间选择，Enter 或空格确认 |
| 任意游戏画面 | Esc 返回上一层；在标题菜单按 Esc 关闭窗口 |

宠物状态随时间变化，退出房间或关闭游戏窗口时写入存档。重开后在标题菜单按 4 恢复。存档位于项目根目录 `.local/MyPet/save.bin`，使用固件的 76 字节记录格式。桌面运行时**不加载**刷机镜像，只读 `assets/` 下已提取的资源与数据。

## 固件来源

游戏来自 `X458ZCEK1.s3` 的 G133 MyPet，回调入口为 `0x238022`，共用调度器为 `0x20D7AC`。`game_flow.py` 是把固件 Thumb 基本块静态翻译成的 Python，保留地址标签与底层 RAM 布局，代码位于 `src/sgh_x458/mypet/`。`game.py` 接入共用运行层并实现 ARM 软浮点规则，`layout.py` 保存 ROM 和 RAM 地址。

- 主状态在 RAM `0x0103F740`，存档缓冲为 `0x12DF454`，帧缓冲为 `0x12C5F60–0x12CFF5F`。游戏代码主要位于 ROM `0x238000–0x23A000`。
- 图像区间 `0x61ABB8–0x653DA9`，共 217 张索引色位图；菜单和退出画面还复用 `0x5860F0` 起的共享图。老式菜单位图和运行时常量位于 `0x65C3E3` 之后。
- SMAF 区间 `0x653DA9–0x65C3E3`，共 9 段。`assets/manifest.json` 记录地址、长度和哈希，WAV 由 Yamaha MA-3 重新渲染为 48 kHz、16 位立体声。
- 主菜单每 500 ms 重绘，帮助自动翻页定时器 3000 ms，宠物房间每 250 ms 更新一次。
- 宠物状态更新调用四条 Thumb→ARM 单精度软浮点桩。地址依次为 `0x14B9A0`（整数转浮点）、`0x14BB4C`（乘）、`0x14C174`（加）和 `0x14BD60`（浮点转整数）。`game.py` 使用 IEEE-754 运算覆盖这四条规则，固定时钟的 RAM 对照已验证结果与原版一致。
- 打开菜单前回调先收到初始化事件 11，帮助翻页使用事件 10，退出宠物房间以事件 2 写回存档。
- 简体中文探针记录的菜单、帮助和开场图像地址分别是 `0x65C57C`、`0x62221E` 及 `0x648E0D`、`0x645F37`。开场 SMAF 位于 `0x6566F3`，长 2180 字节，调用返回地址为 `0x2380C4`。

## 验证与重新提取

```powershell
.\.venv\Scripts\python.exe -B -m tools.mypet.verify
.\.venv\Scripts\python.exe -B -m tools.mypet.trace
.\.venv\Scripts\python.exe -B -m tools.mypet.extract
```

`verify.py` 用 Unicorn 执行原始 ARM 回调，逐步对照 RGB565 帧、除堆栈外的整块 RAM、定时器队列、音频请求和存档字节，覆盖三种语言的菜单、帮助多页、开场、全部按键、六个图标、长时间更新以及退出后继续游戏。`trace.py` 用多个探针实例覆盖全部交互路径，完整运行约 9 分钟，结果写入 `tools/mypet/trace.json`；单独运行 `python -m tools.mypet.probe --trace` 只会写 `.local/mypet/probe-trace.json`，不会覆盖它。真机屏幕颜色、扬声器音色和长时间养成结果仍待实测。

若需重新渲染音频，使用 32 位 Windows Python 运行 `python -m tools.render_audio <ma3smwemu.dll> --assets src/sgh_x458/mypet/assets`。
