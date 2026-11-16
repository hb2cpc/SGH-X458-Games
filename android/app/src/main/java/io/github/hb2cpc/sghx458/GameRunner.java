package io.github.hb2cpc.sghx458;

import android.content.Context;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import java.io.File;

final class GameRunner {
    interface Listener {
        void frame(byte[] pixels, boolean score, boolean fighterBattle);
        void finished();
        void failed();
    }

    private final HandlerThread thread = new HandlerThread("SGH-X458");
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Handler worker;
    private final Listener listener;
    private final boolean fighter;
    private GameAudio sound;
    private PyObject game;
    private long previous;
    private boolean running;
    private boolean score;
    private boolean battle;
    private boolean firstFrame = true;
    private boolean closing;

    GameRunner(Context context, String id, String options, int volume, Listener listener) {
        this.listener = listener;
        fighter = id.equals("x_fighter");
        Context application = context.getApplicationContext();
        thread.start();
        worker = new Handler(thread.getLooper());
        worker.post(() -> execute(() -> {
            if (!Python.isStarted()) Python.start(new AndroidPlatform(application));
            sound = new GameAudio(application.getAssets(), id, volume);
            File saves = new File(application.getFilesDir(), "saves");
            game = Python.getInstance().getModule("game_session").callAttr(
                    "GameSession", id, saves.getAbsolutePath(), sound, options);
            resumeOnWorker();
        }));
    }

    void key(String key, boolean down) {
        worker.post(() -> execute(() -> {
            if (!running) return;
            game.callAttr("key", key, down);
            if (fighter && down) publish(game.callAttr("take_frame"));
        }));
    }

    void typeScore(String text) {
        worker.post(() -> execute(() -> {
            if (running) game.callAttr("type_score", text);
        }));
    }

    void background() {
        worker.post(() -> execute(() -> {
            if (!running) return;
            running = false;
            worker.removeCallbacks(tick);
            sound.background(true);
            game.callAttr("suspend");
        }));
    }

    void foreground() {
        worker.post(() -> execute(this::resumeOnWorker));
    }

    private void resumeOnWorker() {
        if (running || game == null || closing) return;
        sound.background(false);
        running = true;
        previous = SystemClock.uptimeMillis();
        worker.post(tick);
    }

    void close() {
        worker.post(() -> {
            if (closing) return;
            closeOnWorker();
            main.post(listener::finished);
        });
    }

    private void closeOnWorker() {
        if (closing) return;
        closing = true;
        running = false;
        worker.removeCallbacks(tick);
        try {
            if (game != null) game.callAttr("close");
        } catch (RuntimeException error) {
            Log.e("SGHX458", "Could not save game on exit", error);
            main.post(listener::failed);
        } finally {
            if (sound != null) sound.stop();
            game = null;
            thread.quitSafely();
        }
    }

    private void execute(Runnable action) {
        if (closing) return;
        try {
            action.run();
        } catch (RuntimeException error) {
            Log.e("SGHX458", "Game session failed", error);
            closeOnWorker();
            main.post(listener::failed);
        }
    }

    private final Runnable tick = () -> execute(this::step);

    private void step() {
        if (!running) return;
        long started = SystemClock.uptimeMillis();
        int elapsed = (int) Math.min(started - previous, 100);
        previous = started;
        if (game.callAttr("is_closed").toBoolean()) {
            closeOnWorker();
            main.post(listener::finished);
            return;
        }
        publish(game.callAttr("tick", elapsed));
        worker.postAtTime(tick, Math.max(started + 16, SystemClock.uptimeMillis() + 1));
    }

    private void publish(PyObject result) {
        boolean nextScore = game.callAttr("score_entry").toBoolean();
        boolean nextBattle = game.callAttr("in_battle").toBoolean();
        if (firstFrame || result != null || score != nextScore || battle != nextBattle) {
            byte[] pixels = result == null ? null : result.toJava(byte[].class);
            score = nextScore;
            battle = nextBattle;
            firstFrame = false;
            main.post(() -> listener.frame(pixels, nextScore, nextBattle));
        }
    }
}
