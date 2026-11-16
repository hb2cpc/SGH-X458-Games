"""MIDP services used by the X458 Java games."""

from collections import deque
from io import BytesIO
import json
from zipfile import ZipFile

from . import read_asset
from .desktop import Sound, write_record
from .java_graphics import Graphics, load_fonts
from .java_services import CLDC, java_bytes, native_bytes
from .java_vm import JavaError, Machine
from .session import HEIGHT, WIDTH


LCDUI = "javax/microedition/lcdui/"
RMS = "javax/microedition/rms/"
PHONE_SIZE = WIDTH, HEIGHT
# X458ZCEK1 system property Display.HEIGHT (ROM 0x1365A8). Canvas.getHeight() returns it,
# and the screen Graphics clamps setClip to 128x144. The 16 rows below belong to the
# firmware's soft-key bar; Java only reaches them through an unclamped repaint clip.
CANVAS_HEIGHT = 144
# Handset time per drawn pixel, calibrated with java_vm.BYTECODE_US (see the note there).
PIXEL_US = 4.4
# Native getGameAction (ROM 0x1313EC). Only the navigation keys map to directions and FIRE;
# GAME_A..GAME_D are 7, 9, * and #. Soft keys, C and the other digits return 0, and any
# other code makes Canvas.getGameAction throw IllegalArgumentException.
GAME_ACTIONS = {
    -1: 1, -2: 6, -3: 2, -4: 5, -5: 8,
    ord("7"): 9, ord("9"): 10, ord("*"): 11, ord("#"): 12,
    **{code: 0 for code in (-6, -7, -8, -10, -11, -12, *b"01234568")},
}


class Midlet(CLDC):
    def __init__(self, assets, saves, volume=0, *, epoch=None, drawing=None, sound=None):
        if drawing is None:
            import pygame as drawing
        self.drawing = drawing
        self.assets = assets
        self.manifest = json.loads((assets / "manifest.json").read_bytes())
        self.archive = BytesIO(read_asset(assets / "runtime-data.bin"))
        super().__init__(ZipFile(self.archive), epoch)
        self.vm = Machine(json.loads(self.resources.read("classes.json")), self)
        self.fonts = load_fonts(json.loads(self.resources.read("fonts.json")), drawing)
        self.saves = saves
        self.record_stores = {}
        self.images = {}
        self.diagnostics = []
        self.midlet = None
        self.current = None
        self.pending = None
        # The MIDP event thread delivers key events and repaints one at a time, in order.
        self.events = deque()
        self.dispatcher = None
        # ``back`` is the MIDP screen buffer the canvas paints into. ``surface`` is the LCD:
        # the firmware's Display.refresh copies only the repainted rectangle across.
        self.back = drawing.Surface(PHONE_SIZE, depth=16)
        self.back.fill((255, 255, 255))
        self.surface = self.back.copy()
        self.closed = False
        self.frame_number = 0
        self.audio = {clip["resource"]: clip["address"][2:] for clip in self.manifest["audio"]}
        self.sound = sound
        if self.sound is None:
            self.sound = Sound(lambda request: assets / "audio/firmware_wav" / (request + ".wav"),
                               enabled=volume > 0)
            if self.sound.channel is not None:
                self.sound.channel.set_volume(volume / 100)

    def boot(self):
        self.clock.spawn(self.start())
        self.advance(0)

    def start(self):
        owner = self.manifest["midlet"]
        self.midlet = yield from self.vm.new(owner)
        yield from self.vm.call(owner, "<init>", "()V", [self.midlet])
        yield from self.vm.event(self.midlet, "startApp", "()V")

    def key(self, code, released=False):
        if self.current is not None:
            self.post(("keyReleased" if released else "keyPressed", code))
            self.advance(0)

    def advance(self, elapsed):
        self.clock.advance(elapsed)

    def run_until(self, ready, limit=10_000):
        """Give the handset up to ``limit`` ms of game time to reach ``ready()``."""
        for _ in range(0, limit, 16):
            if ready():
                return
            self.advance(16)

    def post(self, event):
        if event != "repaint" or event not in self.events:
            self.events.append(event)
        if self.dispatcher is None or self.dispatcher.done:
            self.dispatcher = self.clock.spawn(self.dispatch())

    def dispatch(self):
        while self.events:
            event = self.events.popleft()
            if event == "repaint":
                if self.current is not None:
                    yield from self.repaint(self.current)
            elif self.current is not None:
                yield from self.vm.event(self.current, event[0], "(I)V", event[1])

    def shutdown(self):
        if self.midlet is not None and not self.closed:
            if self.current is not None and self.current.name == "BubbleGame":
                self.key(-8)  # Run the game's original save-and-return action.
                self.run_until(lambda: not self.events and self.dispatcher.done)
            task = self.clock.spawn(self.vm.event(self.midlet, "destroyApp", "(Z)V", True))
            self.run_until(lambda: task.done)
        self.resources.close()
        self.archive.close()

    def request_repaint(self, area=(0, 0, *PHONE_SIZE)):
        # Displayable.repaint() asks for (0, 0, 128, Display.HEIGHT + 16), the whole LCD.
        rect = self.back.get_rect().clip(self.drawing.Rect(area))
        if rect:
            self.pending = rect if self.pending is None else self.pending.union(rect)
            self.post("repaint")

    def repaint(self, canvas):
        if self.current is canvas and self.pending is not None:
            dirty, self.pending = self.pending, None
            graphics = Graphics(self.back, self.drawing, self.fonts, (0, 0, WIDTH, CANVAS_HEIGHT), dirty)
            yield from self.vm.event(canvas, "paint", "(Ljavax/microedition/lcdui/Graphics;)V", graphics)
            self.surface.blit(self.back, dirty, dirty)
            self.frame_number += 1

    def change_display(self, current):
        previous = self.current
        if current is previous:
            return
        self.current = current
        if previous is not None:
            yield from self.vm.event(previous, "hideNotify", "()V")
        if current is not None:
            self.request_repaint()
            yield from self.vm.event(current, "showNotify", "()V")
        else:
            self.pending = None

    def invoke(self, owner, name, desc, args):
        if owner.startswith(LCDUI):
            match owner[len(LCDUI):]:
                case "Canvas":
                    if name == "getWidth":
                        return WIDTH
                    if name == "getHeight":
                        return CANVAS_HEIGHT
                    if name == "getGameAction":
                        if args[1] not in GAME_ACTIONS:
                            raise JavaError("java/lang/IllegalArgumentException")
                        return GAME_ACTIONS[args[1]]
                    if name == "repaint" and args[0] is self.current:
                        self.request_repaint(*([args[1:]] if args[1:] else []))
                    if name == "serviceRepaints":
                        return self.repaint(args[0])
                    return None
                case "Display":
                    if name == "getDisplay":
                        return self
                    if name == "getCurrent":
                        return self.current
                    if name == "setCurrent":
                        return self.change_display(args[-1])
                    return True if name == "isColor" else 65536
                case "Graphics":
                    graphics = args[0]
                    before = graphics.pixels
                    result = graphics.draw(name, *args[1:])
                    self.vm.cost += (graphics.pixels - before) * PIXEL_US
                    return result
                case "Image":
                    if name == "getGraphics":
                        return Graphics(args[0], self.drawing, self.fonts)
                    return self.image(*args)
                case "Font":
                    # 0x1311F8 selects SmallFontB for bold SMALL text.
                    _, style, size = args
                    return self.fonts[size, style & 1 if size == 8 else 0]
                case "Displayable":
                    # Fun2Link also binds the same soft-key actions directly on its Canvas.
                    return None
                case "Command" | "Alert":
                    return None
        if owner == "javax/microedition/midlet/MIDlet":
            if name == "notifyDestroyed":
                self.closed = True
            return None
        if owner == RMS + "RecordStore":
            return self.record_store(name, *args)
        if owner == "com/samsung/util/AudioClip":
            return self.clip(name, *args)
        return super().invoke(owner, name, desc, args)

    def image(self, *args):
        if len(args) == 2:
            image = self.drawing.Surface(tuple(args), depth=16)
            image.fill((255, 255, 255))  # A mutable MIDP image starts out white.
            return image
        if len(args) == 1:
            path = args[0]
            if path not in self.images:
                data = self.resource(path)
                if data is None:
                    raise JavaError("java/io/IOException", path)
                self.images[path] = self.drawing.image.load(BytesIO(data), "asset.png")
            return self.images[path]
        return self.drawing.image.load(BytesIO(native_bytes(*args)), "asset.png")

    def clip(self, name, clip, *args):
        # com.samsung.util.AudioClip in the ROM keeps a ``playing`` flag per clip: play()
        # is ignored while it is set, and only stop() clears it. The handset has one
        # player, so stop() on a flagged clip silences whatever is sounding.
        if name == "<init>":
            path = args[1]
            if path not in self.audio:
                raise JavaError("java/io/IOException", path)
            clip.data = [self.audio[path], False]
        elif name == "play" and not clip.data[1]:
            clip.data[1] = True
            self.sound.play(clip.data[0], loops=max(0, args[0] - 1))
        elif name == "stop" and clip.data[1]:
            clip.data[1] = False
            self.sound.play(None)

    def record_store(self, name, store, *args):
        if name == "openRecordStore":
            return self.open_store(store, args[0])
        if name == "deleteRecordStore":
            self.record_stores.pop(store, None)
            self.store_path(store).unlink(missing_ok=True)
            return None
        if name == "closeRecordStore":
            return None
        records = self.record_stores[store]
        if name == "getNumRecords":
            return len(records)
        if name == "addRecord":
            data = native_bytes(*args)
            records = records + [data]
            self.save_store(store, records)
            return len(records)
        index, *rest = args
        if not 0 < index <= len(records):
            raise JavaError(RMS + "InvalidRecordIDException", str(index))
        data = records[index - 1]
        if name == "getRecordSize":
            return len(data)
        if name == "getRecord":
            if not rest:
                return java_bytes(data)
            target, offset = rest
            target[offset:offset + len(data)] = java_bytes(data)
            return len(data)
        if name == "setRecord":
            records = records.copy()
            records[index - 1] = native_bytes(*rest)
            self.save_store(store, records)
            return None
        raise NotImplementedError(name)

    def store_path(self, store):
        # The original names are short ASCII strings. Encoding also handles path separators.
        return self.saves / (store.encode("utf-8").hex() + ".json")

    def open_store(self, store, create):
        if store not in self.record_stores:
            try:
                data = json.loads(self.store_path(store).read_bytes())
                self.record_stores[store] = [bytes.fromhex(record) for record in data]
            except FileNotFoundError:
                if not create:
                    raise JavaError(RMS + "RecordStoreNotFoundException", store) from None
                self.record_stores[store] = []
            except (OSError, TypeError, ValueError) as error:
                raise JavaError(RMS + "RecordStoreException", store) from error
        return store

    def save_store(self, store, records):
        try:
            write_record(self.store_path(store), json.dumps([data.hex() for data in records]).encode())
        except OSError as error:
            raise JavaError(RMS + "RecordStoreException", store) from error
        self.record_stores[store] = records

