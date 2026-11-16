package io.github.hb2cpc.sghx458;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PorterDuff;
import android.graphics.Rect;
import java.nio.ByteBuffer;

/** Small, unfiltered drawing surface for the handset LCD and Java game images. */
public final class AndroidRaster {
    private final Bitmap bitmap;
    private final Canvas canvas;
    private final Paint paint = new Paint();
    private final Rect clip;

    public AndroidRaster(int width, int height, boolean rgb565) {
        this(Bitmap.createBitmap(width, height,
                rgb565 ? Bitmap.Config.RGB_565 : Bitmap.Config.ARGB_8888));
    }

    private AndroidRaster(Bitmap bitmap) {
        this.bitmap = bitmap;
        canvas = bitmap.isMutable() ? new Canvas(bitmap) : null;
        clip = new Rect(0, 0, width(), height());
    }

    public static AndroidRaster decode(byte[] data) {
        Bitmap bitmap = BitmapFactory.decodeByteArray(data, 0, data.length);
        if (bitmap == null) throw new IllegalArgumentException("Invalid MIDP image");
        return new AndroidRaster(bitmap);
    }

    public int width() { return bitmap.getWidth(); }
    public int height() { return bitmap.getHeight(); }

    public AndroidRaster copy() {
        return new AndroidRaster(bitmap.copy(bitmap.getConfig(), true));
    }

    public void setClip(int x, int y, int width, int height) {
        clip.set(x, y, x + width, y + height);
    }

    private void begin(int color) {
        canvas.save();
        canvas.clipRect(clip);
        paint.setColor(0xff000000 | color);
    }

    public void fill(int color) {
        begin(color);
        canvas.drawColor(paint.getColor());
        canvas.restore();
    }

    public void clear() {
        canvas.drawColor(Color.TRANSPARENT, PorterDuff.Mode.CLEAR);
    }

    public void pixel(int x, int y, int color) {
        if (clip.contains(x, y)) bitmap.setPixel(x, y, 0xff000000 | color);
    }

    public void blit(AndroidRaster source, int x, int y, int sx, int sy, int width, int height) {
        begin(0);
        canvas.drawBitmap(source.bitmap, new Rect(sx, sy, sx + width, sy + height),
                new Rect(x, y, x + width, y + height), paint);
        canvas.restore();
    }

    public void line(int color, int x, int y, int u, int v) {
        // Integer endpoints, including the last pixel.
        int dx = Math.abs(u - x);
        int dy = -Math.abs(v - y);
        int sx = x < u ? 1 : -1;
        int sy = y < v ? 1 : -1;
        int error = dx + dy;
        for (;;) {
            pixel(x, y, color);
            if (x == u && y == v) return;
            int twice = error * 2;
            if (twice >= dy) { error += dy; x += sx; }
            if (twice <= dx) { error += dx; y += sy; }
        }
    }

    public void rect(int color, int x, int y, int width, int height, int stroke, int radius) {
        if (width <= 0 || height <= 0) return;
        begin(color);
        if (stroke != 0) {
            canvas.drawRect(x, y, x + width, y + 1, paint);
            canvas.drawRect(x, y + height - 1, x + width, y + height, paint);
            canvas.drawRect(x, y, x + 1, y + height, paint);
            canvas.drawRect(x + width - 1, y, x + width, y + height, paint);
        } else if (radius > 0) {
            canvas.drawRoundRect(x, y, x + width, y + height, radius, radius, paint);
        } else {
            canvas.drawRect(x, y, x + width, y + height, paint);
        }
        canvas.restore();
    }

    public void ellipse(int color, int x, int y, int width, int height) {
        begin(color);
        canvas.drawOval(x, y, x + width, y + height, paint);
        canvas.restore();
    }

    public void polygon(int color, int[] xs, int[] ys) {
        Path path = new Path();
        path.moveTo(xs[0], ys[0]);
        for (int i = 1; i < xs.length; i++) path.lineTo(xs[i], ys[i]);
        path.close();
        begin(color);
        canvas.drawPath(path, paint);
        canvas.restore();
    }

    public byte[] frame() {
        ByteBuffer output = ByteBuffer.allocate(bitmap.getByteCount());
        bitmap.copyPixelsToBuffer(output);
        return output.array();
    }
}
