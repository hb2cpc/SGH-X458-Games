"""CLDC services required by the bundled games, with a shared game-time clock."""

from heapq import heappop, heappush
from io import BytesIO
from itertools import count
from time import time_ns

from .java_vm import Busy, JavaError, signed


def java_bytes(data):
    return [signed(byte, 8) for byte in data]


def native_bytes(data, offset=0, length=None):
    return bytes(value & 255 for value in data[offset:None if length is None else offset + length])


def sleep(milliseconds):
    yield max(1, milliseconds)


class Task:
    def __init__(self, body):
        self.body = body
        self.done = False
        self.waiters = []


class Clock:
    def __init__(self, epoch=None):
        self.now = 0
        self.target = 0
        self.epoch = time_ns() // 1_000_000 if epoch is None else epoch
        self.queue = []
        self.sequence = count()

    def enqueue(self, task, delay):
        heappush(self.queue, (self.now + delay, next(self.sequence), task))

    def spawn(self, body, delay=0):
        task = Task(body)
        self.enqueue(task, delay)
        return task

    def advance(self, elapsed):
        # ``target`` follows the desktop's elapsed time. ``now`` is the handset CPU's time:
        # it runs ahead of the target while the CPU is still busy with earlier work.
        self.target += elapsed
        while self.queue and max(self.queue[0][0], self.now) <= self.target:
            due, _, task = heappop(self.queue)
            self.now = max(self.now, due)
            try:
                request = next(task.body)
            except StopIteration:
                task.done = True
                for waiter in task.waiters:
                    self.enqueue(waiter, 0)
                task.waiters.clear()
            else:
                if isinstance(request, Busy):
                    self.now += request
                    self.enqueue(task, 0)
                elif isinstance(request, Task):
                    if request.done:
                        self.enqueue(task, 0)
                    else:
                        request.waiters.append(task)
                else:
                    self.enqueue(task, request)
        self.now = max(self.now, self.target)

    @property
    def millis(self):
        return int(self.now)


class CLDC:
    def __init__(self, resources, epoch):
        self.resources = resources
        self.clock = Clock(epoch)
        self.random_number = 0

    def resource(self, path):
        try:
            return self.resources.read(path.lstrip("/"))
        except KeyError:
            return None

    def static_field(self, owner, name, descriptor):
        if (owner, name) == ("java/lang/System", "out"):
            return self
        raise NotImplementedError(f"{owner}.{name}:{descriptor}")

    def invoke(self, owner, name, desc, args):
        if owner == "java/lang/Object":
            if name == "<init>":
                return None
            if name == "getClass":
                return args[0].name
        if owner == "java/lang/Class":
            cls = args[0]
            if name == "getName":
                return cls.replace("/", ".")
            path = args[1]
            if not path.startswith("/") and "/" in cls:
                path = f"{cls.rpartition('/')[0]}/{path}"
            data = self.resource(path)
            return None if data is None else BytesIO(data)
        if owner == "java/lang/Math":
            return {"abs": lambda value: signed(abs(value), 32), "min": min, "max": max}[name](*args)
        if owner == "java/lang/Integer":
            if name == "toString":
                return str(args[0])
            try:
                value = int(args[0], 10 if len(args) == 1 else args[1])
                if value != signed(value, 32):
                    raise ValueError()
                return value
            except (TypeError, ValueError) as error:
                raise JavaError("java/lang/NumberFormatException", str(args[0])) from error
        if owner == "java/lang/String":
            if name == "<init>":
                args[0].data = ""
                return None
            return java_string(args[0]) == java_string(args[1]) if args[1] is not None else False
        if owner == "java/lang/StringBuffer":
            return string_buffer(name, desc, *args)
        if owner == "java/lang/System":
            return self.clock.epoch + self.clock.millis if name == "currentTimeMillis" else None
        if owner == "java/lang/Thread":
            return self.thread(name, *args)
        if owner == "java/util/Timer":
            return self.timer(name, *args)
        if owner == "java/util/TimerTask":
            if name == "cancel":
                active = not args[0].data
                args[0].data = True
                return active
            return None
        if owner == "java/util/Random":
            rng = args[0]
            if name == "<init>":
                self.random_number += 1
                seed = args[1] if len(args) == 2 else self.clock.epoch + self.clock.millis + self.random_number
                rng.data = (seed ^ 0x5DEECE66D) & ((1 << 48) - 1)
                return None
            rng.data = (rng.data * 0x5DEECE66D + 11) & ((1 << 48) - 1)
            return signed(rng.data >> 16, 32)
        if owner in ("java/util/Stack", "java/util/Vector"):
            return collection(name, *args)
        if owner.startswith("java/io/"):
            return stream(name, owner, *args)
        if (owner, name) == ("java/lang/Throwable", "printStackTrace"):
            self.diagnostics.append(str(args[0]))
            return None
        raise NotImplementedError(f"{owner}.{name}{desc}")

    def thread(self, name, *args):
        if name in ("sleep", "yield"):
            return sleep(args[0] if args else 1)
        thread = args[0]
        if name == "<init>":
            thread.data = (args[1] if len(args) > 1 else thread, None)
        elif name == "start":
            target, task = thread.data
            if task is not None:
                raise JavaError("java/lang/IllegalThreadStateException")
            thread.data = (target, self.clock.spawn(self.vm.event(target, "run", "()V")))
        elif name == "join":
            _, task = thread.data
            if task is not None and not task.done:
                return join(task)
        return None

    def timer(self, name, timer, *args):
        if name == "<init>":
            timer.data = []
        elif name == "cancel":
            for task in timer.data:
                task.data = True
            timer.data.clear()
        else:
            task, delay, period = args
            timer.data[:] = [previous for previous in timer.data if not previous.data]
            timer.data.append(task)
            self.clock.spawn(self.repeat(task, period, name == "scheduleAtFixedRate"), delay)

    def repeat(self, task, period, fixed_rate):
        # java.util.Timer: a fixed-rate task is due ``period`` after its previous due time,
        # a fixed-delay task ``period`` after its previous run actually started.
        due = self.clock.now
        while not task.data:
            started = self.clock.now
            yield from self.vm.event(task, "run", "()V")
            due = (due if fixed_rate else started) + period
            yield max(0, due - self.clock.now)


def join(task):
    yield task


def java_string(value):
    if value is None:
        return "null"
    if hasattr(value, "name") and value.name == "java/lang/String":
        return value.data
    return str(value)


def string_buffer(name, descriptor, buffer, *args):
    if name == "<init>":
        buffer.data = ""
    elif name == "append":
        buffer.data += chr(args[0]) if descriptor.startswith("(C)") else java_string(args[0])
        return buffer
    elif name == "delete":
        start, end = args
        buffer.data = buffer.data[:start] + buffer.data[end:]
        return buffer
    elif name == "length":
        return len(buffer.data)
    elif name == "toString":
        return buffer.data
    return None


def collection(name, obj, *args):
    if name == "<init>":
        obj.data = []
    elif name in ("push", "addElement"):
        obj.data.append(args[0])
        return args[0]
    elif name in ("empty", "isEmpty"):
        return not obj.data
    elif name == "size":
        return len(obj.data)
    elif name == "removeAllElements":
        obj.data.clear()
    elif name == "pop":
        return obj.data.pop()
    elif name == "peek":
        return obj.data[-1]
    elif name == "elementAt":
        return obj.data[args[0]]
    elif name == "removeElementAt":
        del obj.data[args[0]]
    return None


def stream(name, owner, obj, *args):
    if name == "<init>":
        if owner == "java/io/ByteArrayOutputStream":
            obj.data = BytesIO()
        elif owner == "java/io/ByteArrayInputStream":
            obj.data = BytesIO(native_bytes(*args))
        else:
            obj.data = args[0].data if hasattr(args[0], "data") else args[0]
        return None
    if name == "println":
        return None
    data = obj.data if hasattr(obj, "data") else obj
    if name == "read":
        if not args:
            chunk = data.read(1)
            return chunk[0] if chunk else -1
        target = args[0]
        offset, length = args[1:] if len(args) > 1 else (0, len(target))
        chunk = data.read(length)
        target[offset:offset + len(chunk)] = java_bytes(chunk)
        return len(chunk) if chunk or not length else -1
    if name in ("readShort", "readInt"):
        size = 2 if name == "readShort" else 4
        chunk = data.read(size)
        if len(chunk) != size:
            raise JavaError("java/io/IOException", "unexpected end of data")
        return int.from_bytes(chunk, "big", signed=True)
    if name == "writeInt":
        data.write(signed(args[0], 32).to_bytes(4, "big", signed=True))
    elif name == "toByteArray":
        return java_bytes(data.getvalue())
    return None

