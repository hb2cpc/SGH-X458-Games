"""Decode the SGH-X458's preverified Java 1.1 class files offline."""

from io import BytesIO
from struct import unpack


def read_class(data):
    source = BytesIO(data)

    def read(fmt):
        return unpack(">" + fmt, source.read(sum({"B": 1, "H": 2, "I": 4, "i": 4, "q": 8}[c] for c in fmt)))

    def u2():
        return read("H")[0]

    def blob():
        return source.read(read("I")[0])

    if source.read(8) != bytes.fromhex("cafebabe0003002d"):
        raise ValueError("Expected a preverified Java 45.3 class")
    pool = [None]
    count = u2()
    while len(pool) < count:
        tag = read("B")[0]
        if tag == 1:
            value = source.read(u2()).replace(b"\xc0\x80", b"\0").decode("utf-8", "surrogatepass")
        elif tag in (7, 8):
            value = u2()
        elif tag in (9, 10, 11, 12):
            value = read("HH")
        elif tag in (3, 5):
            value = read("i" if tag == 3 else "q")[0]
        else:
            raise ValueError(f"Unsupported constant tag {tag}")
        pool.append((tag, value))
        if tag == 5:
            pool.append(None)

    def resolve(index):
        if not index:
            return None
        tag, value = pool[index]
        if tag in (7, 8):
            return resolve(value)
        if tag in (9, 10, 11):
            owner, signature = value
            return [resolve(owner), *resolve(signature)]
        if tag == 12:
            return [resolve(i) for i in value]
        return value

    _, this, parent = read("HHH")
    for _ in range(u2()):
        u2()  # All callable interface methods are dispatched on the receiver.
    fields = []
    for _ in range(u2()):
        flags, name, desc = read("HHH")
        default = None if resolve(desc).startswith(("[", "L")) else 0
        for _ in range(u2()):
            attr = resolve(u2())
            data = blob()
            if attr == "ConstantValue":
                default = resolve(int.from_bytes(data, "big"))
        fields.append([resolve(name), resolve(desc), bool(flags & 8), default])

    methods = []
    for _ in range(u2()):
        flags, name, desc = read("HHH")
        for _ in range(u2()):
            attr = resolve(u2())
            data = blob()
            if attr != "Code":
                continue
            _, locals_count, size = unpack(">HHI", data[:8])
            body = data[8:8 + size]
            size += 8
            catches = []
            for i in range(int.from_bytes(data[size:size + 2], "big")):
                start = size + 2 + 8 * i
                lo, hi, target, exception = unpack(">HHHH", data[start:start + 8])
                catches.append([lo, hi, target, resolve(exception)])
            methods.append([resolve(name), resolve(desc), bool(flags & 8), locals_count,
                            decode(body, resolve), catches])
    return resolve(this), [resolve(parent), fields, methods]


# Indexed constant-pool operands, including interface invocation and array allocation.
POOL_OPS = {0x13, 0x14, *range(0xB2, 0xBA), 0xBB, 0xBD, 0xC0, 0xC5}
ONE_BYTE = {0x10, 0x12, 0x15, 0x16, 0x19, 0x36, 0x37, 0x3A, 0xBC}
BRANCHES = {*range(0x99, 0xA8), 0xC6, 0xC7}
NO_OPERAND = {
    0x00, *range(0x01, 0x0B), *range(0x1A, 0x22), *range(0x2A, 0x2E),
    0x2E, 0x32, 0x33, 0x35, *range(0x3B, 0x43), *range(0x4B, 0x4F),
    0x4F, 0x53, 0x54, 0x56, 0x57, *range(0x59, 0x5D),
    0x60, 0x64, 0x68, 0x6C, 0x70, 0x71, 0x74, 0x75, 0x78, 0x79, 0x7A,
    0x7E, 0x80, 0x81, 0x85, 0x88, 0x91, 0x92, 0x93, 0x94,
    0xAC, 0xB0, 0xB1, 0xBE, 0xBF,
}


def decode(code, resolve):
    instructions = []
    pos = 0
    while pos < len(code):
        address = pos
        op = code[pos]
        pos += 1
        args = []
        if op in POOL_OPS:
            args.append(resolve(int.from_bytes(code[pos:pos + 2], "big")))
            pos += 2
            if op == 0xB9:
                pos += 2
            if op == 0xC5:
                args.append(code[pos])
                pos += 1
        elif op in ONE_BYTE:
            operand = code[pos]
            pos += 1
            args.append(resolve(operand) if op == 0x12 else
                        operand - 256 if op == 0x10 and operand >= 128 else operand)
        elif op == 0x11 or op in BRANCHES:
            operand = int.from_bytes(code[pos:pos + 2], "big", signed=True)
            pos += 2
            args.append(address + operand if op in BRANCHES else operand)
        elif op == 0x84:
            args.extend(unpack(">Bb", code[pos:pos + 2]))
            pos += 2
        elif op in (0xAA, 0xAB):
            pos = (pos + 3) & ~3
            default, first = unpack(">ii", code[pos:pos + 8])
            pos += 8
            if op == 0xAA:
                last = unpack(">i", code[pos:pos + 4])[0]
                pos += 4
                offsets = unpack(f">{last - first + 1}i", code[pos:pos + 4 * (last - first + 1)])
                pairs = zip(range(first, last + 1), offsets)
                pos += 4 * len(offsets)
            else:
                pairs = [unpack(">ii", code[i:i + 8]) for i in range(pos, pos + 8 * first, 8)]
                pos += 8 * first
            args.extend([address + default, {k: address + offset for k, offset in pairs}])
        elif op not in NO_OPERAND:
            raise ValueError(f"Unsupported opcode {op:#04x} at {address:#x}")
        instructions.append([address, op, *args])
    return instructions

