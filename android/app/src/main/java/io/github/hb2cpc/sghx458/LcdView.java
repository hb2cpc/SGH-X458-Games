package io.github.hb2cpc.sghx458;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.view.View;
import java.nio.ByteBuffer;

final class LcdView extends View {
    private final Bitmap lcd = Bitmap.createBitmap(128, 160, Bitmap.Config.RGB_565);
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint pixels = new Paint(0);
    private final RectF frame = new RectF();
    private boolean ready;

    LcdView(Context context, int textColor) {
        super(context);
        pixels.setFilterBitmap(false);
        text.setTextAlign(Paint.Align.CENTER);
        text.setTextSize(14 * getResources().getDisplayMetrics().density);
        text.setColor(textColor);
        setContentDescription("128 × 160 游戏屏幕");
    }

    void show(byte[] pixels) {
        lcd.copyPixelsFromBuffer(ByteBuffer.wrap(pixels));
        ready = true;
        invalidate();
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float scale = Math.min(getWidth() / 128f, getHeight() / 160f);
        if (scale <= 0) return;
        if (scale >= 2) scale = (int) scale;
        float left = Math.round((getWidth() - 128 * scale) / 2);
        float top = Math.round((getHeight() - 160 * scale) / 2);
        frame.set(left, top, left + 128 * scale, top + 160 * scale);
        if (ready) canvas.drawBitmap(lcd, null, frame, pixels);
        else canvas.drawText("载入游戏中…", frame.centerX(), frame.centerY(), text);
    }
}
