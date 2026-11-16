package io.github.hb2cpc.sghx458;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.media.AudioManager;
import android.os.Build;
import android.os.Bundle;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;
import android.widget.ArrayAdapter;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Spinner;
import android.widget.TextView;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashSet;
import java.util.Set;
import org.json.JSONException;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private record Palette(int background, int panel, int line, int ink, int secondary, int accent, int onAccent) {}

    private static final Palette DARK = new Palette(
            0xff11191a, 0xff1e2928, 0xff334440, 0xfff2f5e8, 0xffb8c9c0, 0xffb7e890, 0xff182517);
    private static final Palette LIGHT = new Palette(
            0xfff2f4ec, 0xffffffff, 0xffcfd8cc, 0xff18221d, 0xff566860, 0xff3c7a20, 0xffffffff);
    private static final String[] SPEEDS = {"0.5", "0.75", "1", "1.5", "2"};
    private static final String[] SUFFIX = {"½×", "¾×", "1×", "1.5×", "2×"};
    private static final String[] SCENES = {"menu", "battle", "boss"};
    private static final String[] ITEMS = {"none", "boost", "slow", "life"};

    private record Game(String id, String title, String description, String guide) {}

    private static final Game[] GAMES = {
        new Game("x_fighter", "X-战机", "纵向射击",
                "标题菜单按 1 开始，2 查看最高分，3 查看帮助，4 继续。"
                + "\n进入战斗后用方向键移动，普通射击自动进行。「导弹」和「核弹」可与移动同时操作。"),
        new Game("spacewar", "空间大战", "街机射击",
                "标题菜单按 1 开始，2 查看最高分，3 查看帮助，4 继续。"
                + "\n用方向键改变飞船的移动方向，OK 停止，C 暂停，OK 恢复。7 续关，9 结束。"),
        new Game("mypet", "我的宠物", "宠物养成",
                "标题菜单按 1 开始、3 查看帮助、4 继续。宠物房间用左右键选择功能，OK 确认，C 返回。"),
        new Game("bubble_smile", "BubbleSmile", "泡泡消除",
                "用方向键移动光标，1／3 旋转泡泡。凑成三个及以上同色泡泡。C 或 # 保存并返回。"),
        new Game("fun2link", "Fun2Link", "管道拼接",
                "用方向键移动，5 铺设管道，* 加速流动，C 或 # 返回。"),
        new Game("ultimate_golf", "Ultimate Golf Challenge", "高尔夫",
                "1／3 调整方向，7／9 选杆，0 切换视角。按 5 启动力度条，再按两次锁定力度和击球。"),
    };

    private Palette colors;
    private FrameLayout root;
    private SharedPreferences preferences;
    private GameRunner runner;
    private final Set<String> held = new HashSet<>();
    private AlertDialog scoreDialog;
    private boolean leaving;
    private boolean showingGuide;
    private boolean resumed;
    private ScrollView libraryScroll;
    private int libraryPosition;
    private final OnBackInvokedCallback gameBack = this::sendBack;

    @Override public void onCreate(Bundle state) {
        preferences = getSharedPreferences("options", MODE_PRIVATE);
        boolean light = preferences.getBoolean("light", false);
        colors = light ? LIGHT : DARK;
        setTheme(light ? R.style.AppTheme_Light : R.style.AppTheme);
        super.onCreate(state);
        setVolumeControlStream(AudioManager.STREAM_MUSIC);
        getWindow().setStatusBarColor(Color.TRANSPARENT);
        getWindow().setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= 29) getWindow().setNavigationBarContrastEnforced(false);
        if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        else getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        root = new FrameLayout(this);
        root.setBackgroundColor(colors.background());
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                var safe = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                view.setPadding(safe.left, safe.top, safe.right, safe.bottom);
            } else {
                view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                        insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return insets;
        });
        setContentView(root);
        showLibrary();
    }

    private void showLibrary() {
        root.removeAllViews();
        ScrollView scroll = new ScrollView(this);
        libraryScroll = scroll;
        scroll.setFillViewport(true);
        root.addView(scroll, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout list = column();
        list.setPadding(dp(20), dp(14), dp(20), dp(20));
        scroll.addView(list, new ScrollView.LayoutParams(-1, -2));

        LinearLayout top = row();
        TextView brand = text("ANYCALL  /  SGH-X458", 12, colors.accent(), true);
        brand.setLetterSpacing(.14f);
        top.addView(brand, new LinearLayout.LayoutParams(0, -2, 1));
        boolean light = colors == LIGHT;
        View theme = iconButton(light ? R.drawable.ic_dark : R.drawable.ic_light,
                light ? "切换到暗色主题" : "切换到亮色主题");
        theme.setOnClickListener(view -> {
            preferences.edit().putBoolean("light", !light).apply();
            recreate();
        });
        LinearLayout.LayoutParams themeLayout = new LinearLayout.LayoutParams(dp(44), dp(44));
        themeLayout.setMarginEnd(dp(8));
        top.addView(theme, themeLayout);
        View settings = iconButton(R.drawable.ic_volume, "游戏音量");
        top.addView(settings, new LinearLayout.LayoutParams(dp(44), dp(44)));
        settings.setOnClickListener(view -> showVolume());
        list.addView(top);
        TextView title = text("游戏库", 38, colors.ink(), true);
        list.addView(title);

        for (int index = 0; index < GAMES.length; index++) {
            if (index == 0 || index == 3) {
                addWithGap(list, text(index == 0 ? "内置游戏" : "Java 游戏", 13, colors.accent(), true), -2, 18);
            }
            addWithGap(list, gameCard(GAMES[index]), dp(78), 7);
        }
        if (libraryPosition != 0) scroll.post(() -> scroll.scrollTo(0, libraryPosition));
    }

    private View gameCard(Game game) {
        LinearLayout card = row();
        card.setPadding(dp(9), dp(7), dp(6), dp(7));
        card.setBackground(shape(colors.panel(), colors.line(), 13));
        LinearLayout play = row();
        play.setBackground(touchBackground(colors.panel(), colors.panel(), 8));
        play.setContentDescription(game.title());
        play.setOnClickListener(view -> startGame(game));

        ImageView preview = new ImageView(this);
        preview.setScaleType(ImageView.ScaleType.FIT_CENTER);
        try (InputStream input = getAssets().open("previews/" + game.id() + ".png")) {
            preview.setImageBitmap(BitmapFactory.decodeStream(input));
        } catch (IOException ignored) {
            preview.setImageResource(R.drawable.app_icon);
        }
        play.addView(preview, new LinearLayout.LayoutParams(dp(50), dp(62)));
        LinearLayout labels = column();
        LinearLayout.LayoutParams labelsLayout = new LinearLayout.LayoutParams(0, -2, 1);
        labelsLayout.setMarginStart(dp(12));
        play.addView(labels, labelsLayout);
        labels.addView(text(game.title(), 17, colors.ink(), true));
        addWithGap(labels, text(game.description(), 12, colors.secondary(), false), -2, 2);
        TextView arrow = text("▶", 14, colors.accent(), false);
        arrow.setGravity(Gravity.CENTER);
        play.addView(arrow, new LinearLayout.LayoutParams(dp(28), -1));
        card.addView(play, new LinearLayout.LayoutParams(0, -1, 1));

        TextView configure = button("⋯", 22, false);
        configure.setContentDescription(game.title() + " 设置");
        card.addView(configure, new LinearLayout.LayoutParams(dp(44), dp(44)));
        configure.setOnClickListener(view -> showOptions(game));
        return card;
    }

    private void startGame(Game game) {
        if (runner != null) return;
        libraryPosition = libraryScroll.getScrollY();
        leaving = false;
        root.removeAllViews();
        LinearLayout console = column();
        console.setPadding(dp(14), dp(4), dp(14), dp(8));
        root.addView(console, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout top = row();
        TextView library = button("‹ 游戏库", 13, false);
        top.addView(library, new LinearLayout.LayoutParams(dp(78), dp(44)));
        library.setOnClickListener(view -> requestExit());
        TextView title = text(game.title(), 15, colors.ink(), true);
        title.setPadding(dp(7), 0, dp(7), 0);
        title.setGravity(Gravity.CENTER);
        top.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        TextView help = button("玩法", 13, false);
        help.setOnClickListener(view -> showGuide(game));
        top.addView(help, new LinearLayout.LayoutParams(dp(56), dp(44)));
        console.addView(top, new LinearLayout.LayoutParams(-1, -2));

        LcdView lcd = new LcdView(this, colors.secondary());
        console.addView(lcd, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout actions = row();
        TextView name = button("输入名字", 13, true);
        name.setVisibility(View.GONE);
        name.setOnClickListener(view -> showNameEditor());
        actions.addView(name, new LinearLayout.LayoutParams(0, -1, 1));
        TextView missile = key("导弹", "missile", false);
        TextView bomb = key("核弹", "bomb", false);
        addAction(actions, missile);
        addAction(actions, bomb);
        // The row keeps its height while hidden, so the screen above it never moves.
        actions.setVisibility(View.INVISIBLE);
        console.addView(actions, new LinearLayout.LayoutParams(-1, dp(44)));

        LinearLayout keypad = row();
        keypad.setPadding(0, dp(6), 0, 0);
        keypad.setGravity(Gravity.CENTER_VERTICAL);
        keypad.addView(keyRows(new String[][] {
            {"C", "↑", ""}, {"←", "OK", "→"}, {"", "↓", ""}
        }, new String[][] {
            {"back", "up", ""}, {"left", "ok", "right"}, {"", "down", ""}
        }), new LinearLayout.LayoutParams(0, -2, 1));
        View gap = new View(this);
        keypad.addView(gap, new LinearLayout.LayoutParams(dp(16), 1));
        keypad.addView(keyRows(new String[][] {
            {"1", "2", "3"}, {"4", "5", "6"}, {"7", "8", "9"}, {"*", "0", "#"}
        }, null), new LinearLayout.LayoutParams(0, -2, 1));
        console.addView(keypad, new LinearLayout.LayoutParams(-1, -2));

        runner = new GameRunner(this, game.id(), options(game).toString(), preferences.getInt("volume", 50),
                new GameRunner.Listener() {
                    @Override public void frame(byte[] pixels, boolean score, boolean fighterBattle) {
                        if (isDestroyed() || leaving || !lcd.isAttachedToWindow()) return;
                        if (pixels != null) lcd.show(pixels);
                        actions.setVisibility(score || fighterBattle ? View.VISIBLE : View.INVISIBLE);
                        name.setVisibility(score ? View.VISIBLE : View.GONE);
                        missile.setVisibility(fighterBattle ? View.VISIBLE : View.GONE);
                        bomb.setVisibility(fighterBattle ? View.VISIBLE : View.GONE);
                    }

                    @Override public void finished() { finishGame(lcd); }

                    @Override public void failed() {
                        if (isDestroyed()) return;
                        finishGame(lcd);
                        new AlertDialog.Builder(MainActivity.this).setMessage("游戏运行中断。")
                                .setPositiveButton("确定", null).show();
                    }
                });
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (Build.VERSION.SDK_INT >= 33) getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                OnBackInvokedDispatcher.PRIORITY_DEFAULT, gameBack);
    }

    private void addAction(LinearLayout row, View button) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1);
        params.setMargins(dp(3), 0, dp(3), 0);
        row.addView(button, params);
    }

    private LinearLayout keyRows(String[][] labels, String[][] keys) {
        LinearLayout rows = column();
        for (int y = 0; y < labels.length; y++) {
            LinearLayout row = row();
            for (int x = 0; x < labels[y].length; x++) {
                String label = labels[y][x];
                String code = keys == null ? label : keys[y][x];
                View view = code.isEmpty() ? new View(this) : key(label, code, code.equals("ok"));
                LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(44), 1);
                params.setMargins(dp(2), dp(2), dp(2), dp(2));
                row.addView(view, params);
            }
            rows.addView(row);
        }
        return rows;
    }

    private TextView key(String label, String code, boolean accent) {
        TextView view = button(label, label.length() > 2 ? 13 : 17, accent);
        view.setOnClickListener(button -> {
            sendKey(code, true);
            sendKey(code, false);
        });
        view.setOnTouchListener((button, event) -> {
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN -> {
                    button.setPressed(true);
                    button.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
                    sendKey(code, true);
                }
                case MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    button.setPressed(false);
                    sendKey(code, false);
                }
                default -> { }
            }
            return true;
        });
        return view;
    }

    private void sendKey(String code, boolean down) {
        if (runner == null || leaving) return;
        boolean changed = down ? held.add(code) : held.remove(code);
        if (changed) runner.key(code, down);
    }

    private void releaseKeys() {
        for (String code : held) runner.key(code, false);
        held.clear();
    }

    private void requestExit() {
        if (runner == null || leaving) return;
        releaseKeys();
        leaving = true;
        runner.close();
    }

    private void finishGame(LcdView lcd) {
        if (isDestroyed() || !lcd.isAttachedToWindow()) return;
        runner = null;
        held.clear();
        if (scoreDialog != null) scoreDialog.dismiss();
        showingGuide = false;
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        unregisterGameBack();
        showLibrary();
    }

    private void showNameEditor() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setHint("字母、数字或空格");
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        input.setFilters(new InputFilter[]{new InputFilter.LengthFilter(10)});
        scoreDialog = new AlertDialog.Builder(this).setTitle("输入排行榜名字").setView(input)
                .setNegativeButton("取消", null).setPositiveButton("填入", (dialog, which) -> {
                    if (runner != null) runner.typeScore(input.getText().toString());
                }).create();
        scoreDialog.show();
        input.requestFocus();
        input.post(() -> getSystemService(InputMethodManager.class).showSoftInput(input, InputMethodManager.SHOW_IMPLICIT));
    }

    private void showGuide(Game game) {
        if (runner == null || leaving) return;
        releaseKeys();
        showingGuide = true;
        runner.background();
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle(game.title()).setMessage(game.guide())
                .setPositiveButton("继续游戏", null).create();
        dialog.setOnDismissListener(ignored -> {
            showingGuide = false;
            if (runner != null && !leaving && resumed) runner.foreground();
        });
        dialog.show();
    }

    private void showVolume() {
        LinearLayout box = dialogBody();
        int volume = preferences.getInt("volume", 50);
        TextView value = text(volumeLabel(volume), 16, colors.ink(), true);
        box.addView(value);
        SeekBar bar = new SeekBar(this);
        bar.setMax(100);
        bar.setProgress(volume);
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                value.setText(volumeLabel(progress));
            }
            @Override public void onStartTrackingTouch(SeekBar seekBar) {}
            @Override public void onStopTrackingTouch(SeekBar seekBar) {}
        });
        addWithGap(box, bar, -2, 12);
        new AlertDialog.Builder(this).setTitle("游戏音量").setView(box).setNegativeButton("取消", null)
                .setPositiveButton("保存", (dialog, which) -> preferences.edit()
                        .putInt("volume", bar.getProgress()).apply()).show();
    }

    private String volumeLabel(int volume) {
        return volume == 0 ? "静音" : volume + "%";
    }

    private JSONObject options(Game game) {
        try {
            return new JSONObject(preferences.getString(game.id(), "{}"));
        } catch (JSONException error) {
            return new JSONObject();
        }
    }

    private void showOptions(Game game) {
        JSONObject saved = options(game);
        LinearLayout box = dialogBody();
        Spinner speed = select(box, "游戏倍速", SUFFIX, indexOf(SPEEDS, saved.optString("speed", "1")));
        boolean fighter = game.id().equals("x_fighter");
        boolean spacewar = game.id().equals("spacewar");
        Spinner scene = null, stage = null, aircraft = null, item = null;
        EditText amount = null, progress = null;
        CheckBox invincible = null, shield = null, upgraded = null;
        if (fighter || spacewar) {
            scene = select(box, "进入场景", fighter ? new String[]{"标题菜单", "战斗进度", "Boss 战"}
                    : new String[]{"标题菜单", "直接进入关卡"},
                    fighter ? indexOf(SCENES, saved.optString("scene")) : ("stage".equals(saved.optString("scene")) ? 1 : 0));
            String[] stages = new String[fighter ? 3 : 10];
            for (int i = 0; i < stages.length; i++) stages[i] = Integer.toString(i + 1);
            stage = select(box, "关卡", stages, saved.optInt("stage", 1) - 1);
            amount = number(box, fighter ? "初始炸弹（0–10）" : "初始后备机（0–100）",
                    saved.optInt(fighter ? "bombs" : "lives", 3), false);
            invincible = check(box, "无敌", saved.optBoolean("invincible"));
            if (fighter) {
                aircraft = select(box, "战机", new String[]{"速度+", "攻击+", "防御+"}, saved.optInt("aircraft", 1) - 1);
                progress = number(box, "战斗进度（0–100%）", saved.optDouble("progress", 0), true);
                upgraded = check(box, "强化武器", saved.optBoolean("upgraded"));
                shield = check(box, "初始护盾", "full".equals(saved.optString("shield")));
            } else {
                item = select(box, "初始道具", new String[]{"无", "加速", "敌人减速", "奖命"},
                        indexOf(ITEMS, saved.optString("item")));
            }
        }
        Spinner finalScene = scene, finalStage = stage, finalAircraft = aircraft, finalItem = item;
        EditText finalAmount = amount, finalProgress = progress;
        CheckBox finalInvincible = invincible, finalShield = shield, finalUpgraded = upgraded;
        ScrollView scroll = new ScrollView(this);
        scroll.addView(box);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle(game.title() + " 设置").setView(scroll)
                .setNeutralButton("恢复默认", (ignored, which) -> preferences.edit().remove(game.id()).apply())
                .setNegativeButton("取消", null).setPositiveButton("保存", null).create();
        dialog.show();
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            JSONObject options = new JSONObject();
            try {
                options.put("speed", SPEEDS[speed.getSelectedItemPosition()]);
                if (fighter || spacewar) {
                    int value = Integer.parseInt(finalAmount.getText().toString());
                    int limit = fighter ? 10 : 100;
                    if (value < 0 || value > limit) {
                        finalAmount.setError("请输入 0–" + limit);
                        return;
                    }
                    int position = finalScene.getSelectedItemPosition();
                    options.put("scene", fighter ? SCENES[position] : (position == 0 ? "menu" : "stage"));
                    options.put("stage", finalStage.getSelectedItemPosition() + 1);
                    options.put("invincible", finalInvincible.isChecked());
                    options.put(fighter ? "bombs" : "lives", value);
                    if (fighter) {
                        double percent;
                        try {
                            percent = Double.parseDouble(finalProgress.getText().toString());
                        } catch (NumberFormatException error) {
                            percent = -1;
                        }
                        if (!(percent >= 0 && percent <= 100)) {
                            finalProgress.setError("请输入 0–100");
                            return;
                        }
                        options.put("progress", percent);
                        options.put("aircraft", finalAircraft.getSelectedItemPosition() + 1);
                        options.put("upgraded", finalUpgraded.isChecked());
                        if (finalShield.isChecked()) options.put("shield", "full");
                    } else options.put("item", ITEMS[finalItem.getSelectedItemPosition()]);
                }
                preferences.edit().putString(game.id(), options.toString()).apply();
                dialog.dismiss();
            } catch (NumberFormatException error) {
                finalAmount.setError("请输入整数");
            } catch (JSONException error) {
                throw new IllegalStateException(error);
            }
        });
    }

    private int indexOf(String[] values, String value) {
        for (int i = 0; i < values.length; i++) if (values[i].equals(value)) return i;
        return 0;
    }

    private LinearLayout dialogBody() {
        LinearLayout box = column();
        box.setPadding(dp(24), dp(14), dp(24), dp(10));
        return box;
    }

    private Spinner select(LinearLayout panel, String label, String[] values, int current) {
        addWithGap(panel, text(label, 13, colors.secondary(), true), -2, 8);
        Spinner spinner = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, values);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        spinner.setSelection(Math.max(0, Math.min(current, values.length - 1)));
        panel.addView(spinner, new LinearLayout.LayoutParams(-1, dp(48)));
        return spinner;
    }

    private EditText number(LinearLayout panel, String label, Number value, boolean decimal) {
        addWithGap(panel, text(label, 13, colors.secondary(), true), -2, 8);
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_NUMBER | (decimal ? InputType.TYPE_NUMBER_FLAG_DECIMAL : 0));
        input.setText(value.toString());
        panel.addView(input, new LinearLayout.LayoutParams(-1, dp(48)));
        return input;
    }

    private CheckBox check(LinearLayout panel, String label, boolean checked) {
        CheckBox box = new CheckBox(this);
        box.setText(label);
        box.setChecked(checked);
        panel.addView(box);
        return box;
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        if (runner != null) {
            int code = event.getKeyCode();
            String key = switch (code) {
                case KeyEvent.KEYCODE_DPAD_UP -> "up";
                case KeyEvent.KEYCODE_DPAD_DOWN -> "down";
                case KeyEvent.KEYCODE_DPAD_LEFT -> "left";
                case KeyEvent.KEYCODE_DPAD_RIGHT -> "right";
                case KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_BUTTON_A -> "ok";
                case KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_DEL, KeyEvent.KEYCODE_BUTTON_B -> "back";
                case KeyEvent.KEYCODE_STAR -> "*";
                case KeyEvent.KEYCODE_POUND -> "#";
                default -> code >= KeyEvent.KEYCODE_0 && code <= KeyEvent.KEYCODE_9
                        ? Integer.toString(code - KeyEvent.KEYCODE_0) : null;
            };
            if (key != null) {
                if (event.getRepeatCount() == 0) sendKey(key, event.getAction() == KeyEvent.ACTION_DOWN);
                return true;
            }
        }
        return super.dispatchKeyEvent(event);
    }

    @Override public void onBackPressed() {
        if (runner == null) super.onBackPressed();
        else sendBack();
    }

    private void sendBack() {
        sendKey("back", true);
        sendKey("back", false);
    }

    private void unregisterGameBack() {
        if (Build.VERSION.SDK_INT >= 33) getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(gameBack);
    }

    @Override protected void onPause() {
        resumed = false;
        if (runner != null && !leaving) {
            releaseKeys();
            runner.background();
        }
        super.onPause();
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        if (runner != null && !leaving && !showingGuide) runner.foreground();
    }

    @Override protected void onDestroy() {
        if (runner != null) unregisterGameBack();
        requestExit();
        super.onDestroy();
    }

    private LinearLayout column() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.VERTICAL);
        return view;
    }

    private LinearLayout row() {
        LinearLayout view = new LinearLayout(this);
        view.setGravity(Gravity.CENTER_VERTICAL);
        view.setMotionEventSplittingEnabled(true);
        return view;
    }

    private void addWithGap(LinearLayout parent, View child, int height, int gap) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, height);
        params.topMargin = dp(gap);
        parent.addView(child, params);
    }

    private TextView text(String content, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(content);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private TextView button(String label, int size, boolean accent) {
        TextView view = text(label, size, accent ? colors.onAccent() : colors.ink(), true);
        view.setGravity(Gravity.CENTER);
        view.setBackground(touchBackground(accent ? colors.accent() : colors.panel(), accent ? colors.accent() : colors.line(), 9));
        view.setFocusable(true);
        view.setClickable(true);
        view.setAccessibilityDelegate(new View.AccessibilityDelegate() {
            @Override public void onInitializeAccessibilityNodeInfo(
                    View host, android.view.accessibility.AccessibilityNodeInfo node) {
                super.onInitializeAccessibilityNodeInfo(host, node);
                node.setClassName("android.widget.Button");
            }
        });
        return view;
    }

    private ImageView iconButton(int icon, String description) {
        ImageView view = new ImageView(this);
        view.setImageResource(icon);
        view.setImageTintList(ColorStateList.valueOf(colors.ink()));
        view.setPadding(dp(11), dp(11), dp(11), dp(11));
        view.setBackground(touchBackground(colors.panel(), colors.line(), 9));
        view.setContentDescription(description);
        view.setFocusable(true);
        view.setClickable(true);
        return view;
    }

    private GradientDrawable shape(int color, int border, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), border);
        return drawable;
    }

    private RippleDrawable touchBackground(int color, int border, int radius) {
        return new RippleDrawable(ColorStateList.valueOf(0x5089b79c), shape(color, border, radius), null);
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
