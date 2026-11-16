"""Execute the decoded Java bytecode used by the three bundled SGH-X458 MIDlets."""

from functools import lru_cache
from operator import and_, eq, ge, gt, le, lt, ne, or_
import re
from types import GeneratorType


def signed(value, bits):
    sign = 1 << (bits - 1)
    return ((value + sign) & ((sign << 1) - 1)) - sign


def division(left, right):
    if not right:
        raise JavaError("java/lang/ArithmeticException", "division by zero")
    quotient = abs(left) // abs(right)
    return -quotient if (left < 0) != (right < 0) else quotient


def remainder(left, right):
    return left - division(left, right) * right


@lru_cache(maxsize=None)
def signature(descriptor):
    args, result = descriptor[1:].split(")")
    return re.findall(r"\[*(?:L[^;]+;|[BCDFIJSZ])", args), result


class JavaError(Exception):
    def __init__(self, name, detail=""):
        super().__init__(f"{name}: {detail}")
        self.name = name


class Ref:
    def __init__(self, name):
        self.name = name
        self.fields = {}
        self.data = None


class Method:
    def __init__(self, owner, name, desc, static, locals_count, instructions, catches):
        self.owner = owner
        self.name = name
        self.desc = desc
        self.static = static
        self.locals_count = locals_count
        offsets = {row[0]: i for i, row in enumerate(instructions)}
        self.catches = catches
        self.code = []
        for offset, op, *args in instructions:
            if 0x99 <= op <= 0xA7 or op in (0xC6, 0xC7):
                args[0] = offsets[args[0]]
            elif op in (0xAA, 0xAB):
                args = [offsets[args[0]], {int(key): offsets[value] for key, value in args[1].items()}]
            elif op in (0xB6, 0xB7, 0xB8, 0xB9):
                params, result = signature(args[0][2])
                args.extend((len(params) + (op != 0xB8), result != "V"))
            self.code.append((offset, op, args))
        self.targets = {target: offsets[target] for _, _, target, _ in catches}


# Handset timing model. The X458's KVM interprets bytecode and draws on a slow ARM core, so
# every animation that chains repaint() from paint() is paced by CPU time, not by sleeps.
# The costs are calibrated against footage of the real phone: BubbleSmile's opening fill
# and first clear (11 chained paints, about 7k bytecodes and 50k drawn pixels each) take
# about 2.6 s. Threads are time-sliced like KVM green threads, so a sleeping thread can
# change state while a long paint is still running.
BYTECODE_US = 3
SLICE_US = 1000


class Busy(float):
    """Milliseconds of handset CPU time a task has just used."""


class Machine:
    def __init__(self, classes, host):
        self.host = host
        self.cost = 0  # Handset CPU time used since the last time slice, in microseconds.
        self.parents = {}
        self.fields = {}
        self.statics = {}
        self.methods = {}
        self.resolved_methods = {}
        self.resolved_fields = {}
        self.initialized = set()
        for owner, (parent, fields, methods) in classes.items():
            self.parents[owner] = parent
            for name, desc, static, default in fields:
                (self.statics if static else self.fields)[owner, name, desc] = default
            for name, desc, *body in methods:
                self.methods[owner, name, desc] = Method(owner, name, desc, *body)

    def hierarchy(self, name):
        while name:
            yield name
            name = self.parents.get(name)

    def method(self, owner, name, desc):
        key = owner, name, desc
        if key not in self.resolved_methods:
            self.resolved_methods[key] = next(
                (self.methods[cls, name, desc] for cls in self.hierarchy(owner)
                 if (cls, name, desc) in self.methods), None)
        return self.resolved_methods[key]

    def field(self, owner, name, desc, static):
        key = owner, name, desc, static
        if key not in self.resolved_fields:
            table = self.statics if static else self.fields
            self.resolved_fields[key] = next(
                ((cls, name, desc) for cls in self.hierarchy(owner) if (cls, name, desc) in table),
                (owner, name, desc))
        return self.resolved_fields[key]

    def initialize(self, owner):
        if owner not in self.parents or owner in self.initialized:
            return
        self.initialized.add(owner)
        yield from self.initialize(self.parents[owner])
        if (method := self.methods.get((owner, "<clinit>", "()V"))) is not None:
            yield from self.execute(method, [])

    def new(self, owner):
        yield from self.initialize(owner)
        return Ref(owner)

    def call(self, owner, name, desc, args, *, virtual=False, static=False):
        if static:
            yield from self.initialize(owner)
        target = owner
        if virtual and isinstance(args[0], Ref):
            target = args[0].name
        method = self.method(target, name, desc)
        if method is not None:
            return (yield from self.execute(method, args))
        result = self.host.invoke(owner, name, desc, args)
        if isinstance(result, GeneratorType):
            return (yield from result)
        return result

    def event(self, receiver, name, desc, *args):
        if (method := self.method(receiver.name, name, desc)) is not None:
            yield from self.execute(method, [receiver, *args])

    def execute(self, method, args):
        locals_ = [None] * method.locals_count
        position = 0
        if not method.static:
            locals_[0] = args[0]
            args = args[1:]
            position = 1
        for arg, desc in zip(args, signature(method.desc)[0]):
            locals_[position] = arg
            position += 2 if desc in ("J", "D") else 1
        stack = []
        pop, push = stack.pop, stack.append
        pc = 0
        code = method.code
        while True:
            offset, op, operands = code[pc]
            pc += 1
            self.cost += BYTECODE_US
            if self.cost >= SLICE_US:
                spent, self.cost = self.cost, 0
                yield Busy(spent / 1000)
            try:
                if op == 0x00:
                    continue
                if op == 0x01:
                    push(None)
                elif 0x02 <= op <= 0x08:
                    push(op - 3)
                elif 0x09 <= op <= 0x0A:
                    push(op - 9)
                elif 0x10 <= op <= 0x14:
                    push(operands[0])
                elif op in (0x15, 0x16, 0x19):
                    push(locals_[operands[0]])
                elif op in (0x36, 0x37, 0x3A):
                    locals_[operands[0]] = pop()
                elif 0x1A <= op <= 0x21:
                    push(locals_[(op - 0x1A) % 4])
                elif 0x2A <= op <= 0x2D:
                    push(locals_[op - 0x2A])
                elif 0x3B <= op <= 0x42:
                    locals_[(op - 0x3B) % 4] = pop()
                elif 0x4B <= op <= 0x4E:
                    locals_[op - 0x4B] = pop()
                elif op in (0x2E, 0x32, 0x33, 0x35):
                    index, items = pop(), nonnull(pop())
                    push(items[array_index(items, index)])
                elif op in (0x4F, 0x53, 0x54, 0x56):
                    value, index, items = pop(), pop(), nonnull(pop())
                    if op == 0x54:
                        value = signed(value, 8)
                    elif op == 0x56:
                        value = signed(value, 16)
                    items[array_index(items, index)] = value
                elif op == 0x57:
                    pop()
                elif op == 0x59:
                    push(stack[-1])
                elif op == 0x5A:
                    stack.insert(len(stack) - 2, stack[-1])
                elif op == 0x5B:
                    stack.insert(len(stack) - 3, stack[-1])
                elif op == 0x5C:
                    # All dup2 sites in these games duplicate two category-1 operands.
                    stack.extend(stack[-2:])
                elif op in BINARY:
                    right, left = pop(), pop()
                    bits, fn = BINARY[op]
                    push(signed(fn(left, right), bits))
                elif op in (0x74, 0x75):
                    push(signed(-pop(), 32 if op == 0x74 else 64))
                elif op == 0x84:
                    slot, increment = operands
                    locals_[slot] = signed(locals_[slot] + increment, 32)
                elif op in CONVERSIONS:
                    push(CONVERSIONS[op](pop()))
                elif op == 0x94:
                    right, left = pop(), pop()
                    push((left > right) - (left < right))
                elif 0x99 <= op <= 0x9E:
                    if COMPARE[op - 0x99](pop(), 0):
                        pc = operands[0]
                elif 0x9F <= op <= 0xA4:
                    right, left = pop(), pop()
                    if COMPARE[op - 0x9F](left, right):
                        pc = operands[0]
                elif op in (0xA5, 0xA6):
                    if (pop() is pop()) == (op == 0xA5):
                        pc = operands[0]
                elif op == 0xA7:
                    pc = operands[0]
                elif op in (0xAA, 0xAB):
                    pc = operands[1].get(pop(), operands[0])
                elif op in (0xAC, 0xB0):
                    return pop()
                elif op == 0xB1:
                    return None
                elif op in (0xB2, 0xB3):
                    key = self.field(*operands[0], True)
                    yield from self.initialize(key[0])
                    if op == 0xB3:
                        self.statics[key] = pop()
                    elif key in self.statics:
                        push(self.statics[key])
                    else:
                        push(self.host.static_field(*key))
                elif op in (0xB4, 0xB5):
                    key = self.field(*operands[0], False)
                    if op == 0xB5:
                        value = pop()
                        nonnull(pop()).fields[key] = value
                    else:
                        push(nonnull(pop()).fields.get(key, self.fields.get(key)))
                elif 0xB6 <= op <= 0xB9:
                    (owner, name, desc), argc, returns = operands
                    actual = stack[-argc:] if argc else []
                    if argc:
                        del stack[-argc:]
                    if op != 0xB8:
                        nonnull(actual[0])
                    value = yield from self.call(owner, name, desc, actual, virtual=op in (0xB6, 0xB9),
                                                 static=op == 0xB8)
                    if returns:
                        push(value)
                elif op == 0xBB:
                    push((yield from self.new(operands[0])))
                elif op in (0xBC, 0xBD):
                    push(new_array([pop()], 0 if op == 0xBC else None))
                elif op == 0xBE:
                    push(len(nonnull(pop())))
                elif op == 0xBF:
                    raise nonnull(pop())
                elif op == 0xC0:
                    # The original verified code only casts resources it allocated itself.
                    continue
                elif op == 0xC5:
                    desc, dimensions = operands
                    lengths = stack[-dimensions:]
                    del stack[-dimensions:]
                    push(new_array(lengths, None if desc[dimensions] in "[L" else 0))
                elif op in (0xC6, 0xC7):
                    if (pop() is None) == (op == 0xC6):
                        pc = operands[0]
                else:
                    raise ValueError(f"Unsupported JVM opcode {op:#x}")
            except JavaError as error:
                for lo, hi, target, exception in method.catches:
                    if lo <= offset < hi and catches(error, exception):
                        stack[:] = [error]
                        pc = method.targets[target]
                        break
                else:
                    error.add_note(f"at {method.owner}.{method.name}{method.desc} ({offset})")
                    raise


def nonnull(value):
    if value is None:
        raise JavaError("java/lang/NullPointerException")
    return value


def array_index(items, index):
    if not 0 <= index < len(items):
        raise JavaError("java/lang/ArrayIndexOutOfBoundsException", str(index))
    return index


def new_array(lengths, initial):
    count, *remaining = lengths
    if count < 0:
        raise JavaError("java/lang/NegativeArraySizeException")
    if remaining:
        return [new_array(remaining, initial) for _ in range(count)]
    return [initial] * count


def catches(error, expected):
    if expected in (None, error.name, "java/lang/Exception", "java/lang/Throwable"):
        return True
    if expected == "java/lang/RuntimeException":
        return error.name.startswith("java/lang/")
    return (expected == "javax/microedition/rms/RecordStoreException"
            and error.name.startswith("javax/microedition/rms/"))


COMPARE = (eq, ne, lt, ge, gt, le)
BINARY = {
    0x60: (32, lambda a, b: a + b),
    0x64: (32, lambda a, b: a - b),
    0x68: (32, lambda a, b: a * b),
    0x6C: (32, division), 0x70: (32, remainder), 0x71: (64, remainder),
    0x78: (32, lambda a, b: a << (b & 31)),
    0x79: (64, lambda a, b: a << (b & 63)),
    0x7A: (32, lambda a, b: a >> (b & 31)),
    0x7E: (32, and_), 0x80: (32, or_), 0x81: (64, or_),
}
CONVERSIONS = {
    0x85: lambda n: n, 0x88: lambda n: signed(n, 32), 0x91: lambda n: signed(n, 8),
    0x92: lambda n: n & 65535, 0x93: lambda n: signed(n, 16),
}

