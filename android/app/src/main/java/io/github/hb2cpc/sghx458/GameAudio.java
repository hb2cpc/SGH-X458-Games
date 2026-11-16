package io.github.hb2cpc.sghx458;

import android.content.res.AssetFileDescriptor;
import android.content.res.AssetManager;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.util.Log;
import java.io.IOException;

/** Single-channel firmware audio, owned by the game thread. */
public final class GameAudio {
    private final AssetManager assets;
    private final String game;
    private final float volume;
    private MediaPlayer player;
    private boolean ready;
    private boolean gamePaused;
    private boolean backgrounded;
    private int loops;

    GameAudio(AssetManager assets, String game, int volume) {
        this.assets = assets;
        this.game = game;
        this.volume = volume / 100f;
    }

    public void play(String name, int repeats) {
        stop();
        if (volume == 0) return;
        loops = repeats;
        MediaPlayer next = new MediaPlayer();
        player = next;
        try (AssetFileDescriptor clip = assets.openFd(game + "/" + name + ".ogg")) {
            next.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_GAME)
                    .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build());
            next.setDataSource(clip);
            next.setVolume(volume, volume);
            next.setOnPreparedListener(current -> {
                if (player == current) {
                    ready = true;
                    updatePlayback();
                }
            });
            next.setOnCompletionListener(current -> {
                if (player != current) return;
                if (loops > 0) {
                    loops--;
                    updatePlayback();
                } else stop();
            });
            next.setOnErrorListener((current, what, extra) -> {
                if (player == current) stop();
                Log.w("SGHX458", "Audio error for " + name + ": " + what + ", " + extra);
                return true;
            });
            next.prepareAsync();
        } catch (IOException | RuntimeException error) {
            stop();
            Log.w("SGHX458", "Couldn't load audio " + name, error);
        }
    }

    public void stop() {
        if (player != null) {
            player.release();
            player = null;
        }
        ready = false;
        gamePaused = false;
    }

    public boolean active() { return player != null; }

    public void pauseGame() {
        gamePaused = true;
        updatePlayback();
    }

    public void resumeGame() {
        gamePaused = false;
        updatePlayback();
    }

    void background(boolean value) {
        backgrounded = value;
        updatePlayback();
    }

    private void updatePlayback() {
        if (!ready) return;
        if (gamePaused || backgrounded) {
            if (player.isPlaying()) player.pause();
        } else player.start();
    }
}
