"""Statically translate traced Thumb code from the X458ZCEK1 image into Python blocks.

Each game's extractor subclasses Lowering with its entry points and code ranges,
then writes the generated game_flow.py and the packed runtime-data.bin. This is an
offline reverse-engineering tool; the desktop games never import it.
"""

import re
from struct import pack, unpack_from

from sgh_x458.runtime.session import BOOT_DISPLAY, GAME_CONTROLLER
from sgh_x458.runtime.word_ops import signed


# Device services and library routines that the shared runtime implements in Python.
HAND_WRITTEN = {
    0x14B3A4, 0x14B3EC, 0x14B468, 0x22808E, 0x2280D8, 0x228134, 0x22813E, 0x228148,
    0x22815E, 0x228174, 0x2281F0, 0x228224, 0x2282C4, 0x2283A0, 0x2283AC,
    0x262954, 0x262998, 0x13FF800,
}


def number(value):
    return f"0x{value:X}u"


def branch(address):
    return f"goto L{address:X};"


class Lowering:
    game_entry = None
    hand_written = HAND_WRITTEN
    # Extra block starts that hand-written rules call into directly.
    extra_entries = frozenset()
    extra_leaders = frozenset()
    # Instruction sites replaced by a game-specific operation.
    patched_ops = {}

    def __init__(self, image, trace):
        self.image = image
        self.observed = set()
        for address, length, thumb in trace["blocks"]:
            if thumb and address < len(image):
                self.observed.update(range(address, address + length, 2))
        self.entries = {BOOT_DISPLAY & ~1, GAME_CONTROLLER & ~1, self.game_entry & ~1, *self.extra_entries}
        self.entries.update(address for address, _, thumb in trace["blocks"]
                            if thumb and self.traced_entry(address))
        self.data = set()
        for address, size in trace["reads"]:
            self.mark(address, size)
        self.translated = {}

    def traced_entry(self, address):
        return True

    def mark(self, address, size):
        self.data.update(range(address, address + size))

    def word(self, address):
        return unpack_from("<I", self.image, address)[0]

    def half(self, address):
        return unpack_from("<H", self.image, address)[0]

    def decode(self, a):
        h = self.half(a)
        d, s, n = h & 7, (h >> 3) & 7, (h >> 6) & 7
        r, imm = (h >> 8) & 7, h & 255
        following = a + 2
        targets = [following]
        if h >> 11 < 3:
            mode = h >> 11
            amount = (h >> 6) & 31
            op = f"r[{d}] = shift(p, r[{s}], {amount if amount or mode == 0 else 32}, {mode});"
        elif h >> 11 == 3:
            arg = str(n) if h & 0x400 else f"r[{n}]"
            op = f"r[{d}] = {'sub' if h & 0x200 else 'add'}(p, r[{s}], {arg}, {'1' if h & 0x200 else '0'});"
        elif h >> 13 == 1:
            kind = (h >> 11) & 3
            op = (f"r[{r}] = nz(p, {imm});", f"sub(p, r[{r}], {imm}, 1);",
                  f"r[{r}] = add(p, r[{r}], {imm}, 0);", f"r[{r}] = sub(p, r[{r}], {imm}, 1);")[kind]
        elif h & 0xFC00 == 0x4000:
            x, y = f"r[{d}]", f"r[{s}]"
            op = (
                f"{x} = nz(p, {x} & {y});", f"{x} = nz(p, {x} ^ {y});",
                *(f"{x} = shift(p, {x}, {y} & 255, {mode});" for mode in range(3)),
                f"{x} = add(p, {x}, {y}, p->c);", f"{x} = sub(p, {x}, {y}, p->c);",
                f"{x} = shift(p, {x}, {y} & 255, 3);", f"nz(p, {x} & {y});",
                f"{x} = sub(p, 0, {y}, 1);", f"sub(p, {x}, {y}, 1);", f"add(p, {x}, {y}, 0);",
                f"{x} = nz(p, {x} | {y});", f"{x} = nz(p, {x} * {y});",
                f"{x} = nz(p, {x} & ~{y});", f"{x} = nz(p, ~{y});",
            )[(h >> 6) & 15]
        elif h & 0xFC00 == 0x4400:
            destination = (h & 7) | ((h >> 4) & 8)
            source = (h >> 3) & 15
            kind = (h >> 8) & 3
            src = number(a + 4) if source == 15 else f"r[{source}]"
            if kind == 3:
                if source == 15:
                    return None  # ARM math interworking has an explicit replacement.
                prefix = f"r[14] = {number(following | 1)}; " if h & 0x80 else ""
                op = f"{prefix}next = {src}; goto dispatch;"
                targets = [following] if prefix else []
            elif destination == 15 and kind in (0, 2):
                value = f"{number(a + 4)} + {src}" if kind == 0 else src
                op = f"next = {value}; goto dispatch;"
                targets = self.switch_targets(a) if kind == 0 else []
            else:
                dst = f"r[{destination}]"
                op = (f"{dst} += {src};", f"sub(p, {dst}, {src}, 1);", f"{dst} = {src};")[kind]
        elif h >> 11 == 9:
            at = ((a + 4) & ~3) + imm * 4
            op = f"r[{r}] = {number(self.word(at))};"
        elif h >> 12 == 5:
            addr = f"r[{s}] + r[{n}]"
            kind = (h >> 9) & 7
            op = self.memory(d, addr, (4, 2, 1, 1, 4, 2, 1, 2)[kind], kind >= 3, kind in (3, 7))
        elif 6 <= h >> 12 <= 8:
            size = (4, 1, 2)[(h >> 12) - 6]
            op = self.memory(d, f"r[{s}] + {((h >> 6) & 31) * size}", size, bool(h & 0x800))
        elif h >> 12 == 9:
            op = self.memory(r, f"r[13] + {imm * 4}", 4, bool(h & 0x800))
        elif h >> 12 == 10:
            base = "r[13]" if h & 0x800 else number((a + 4) & ~3)
            op = f"r[{r}] = {base} + {imm * 4};"
        elif h & 0xFF00 == 0xB000:
            op = f"r[13] {'-=' if h & 128 else '+='} {(h & 127) * 4};"
        elif h & 0xF600 == 0xB400:
            pop = bool(h & 0x800)
            registers = [i for i in range(8) if imm & (1 << i)]
            if h & 0x100:
                registers.append(15 if pop else 14)
            if pop:
                reads = [f"r[{reg}] = rd(p, r[13] + {index * 4}, 4);" for index, reg in enumerate(registers)]
                op = " ".join(reads) + f" r[13] += {len(registers) * 4};"
                if 15 in registers:
                    op += " next = r[15]; goto dispatch;"
                    targets = []
            else:
                writes = [f"wr(p, r[13] + {index * 4}, 4, r[{reg}]);" for index, reg in enumerate(registers)]
                op = f"r[13] -= {len(registers) * 4}; " + " ".join(writes)
        elif h >> 12 == 12:
            read = bool(h & 0x800)
            registers = [i for i in range(8) if imm & (1 << i)]
            op = f"temp = r[{r}]; " + " ".join(self.memory(reg, f"temp + {index * 4}", 4, read)
                                                for index, reg in enumerate(registers))
            if not read or r not in registers:
                op += f" r[{r}] = temp + {len(registers) * 4};"
        elif h >> 12 == 13 and (h >> 8) & 15 < 14:
            cond = (h >> 8) & 15
            dest = a + 4 + signed(imm, 8) * 2
            op = f"if (condition(p, {cond})) {{ {branch(dest)} }}"
            targets.append(dest)
        elif h >> 11 == 28:
            dest = a + 4 + signed(h & 2047, 11) * 2
            op = branch(dest)
            targets = [dest]
        elif h >> 11 == 30 and self.half(a + 2) >> 11 in (29, 31):
            low = self.half(a + 2)
            delta = signed(((h & 2047) << 12) | ((low & 2047) << 1), 23)
            dest = a + 4 + delta
            if low >> 11 == 29:
                dest &= ~3
            following = a + 4
            op = f"r[14] = {number(following | 1)}; {branch(dest)}"
            targets = [following, dest]
        else:
            return None
        return self.patched_ops.get(a, op), targets, following

    @staticmethod
    def memory(register, address, size, read, sign=False):
        if not read:
            return f"wr(p, {address}, {size}, r[{register}]);"
        cast = f"(int32_t)(int{size * 8}_t)" if sign else ""
        return f"r[{register}] = {cast}rd(p, {address}, {size});"

    def switch_targets(self, a):
        # ADS Thumb switch: ADR table, LDRB table[index], LSL, ADD PC, offset.
        adr, ldr, shift, jump = (self.half(i) for i in range(a - 6, a + 2, 2))
        register = (adr >> 8) & 7
        if adr >> 11 != 20 or ldr & 0xFE3F != 0x5C00 | (register << 3) | register:
            return []
        if shift != 0x40 | (register << 3) | register or ((jump >> 3) & 15) != register:
            return []
        index = (ldr >> 6) & 7
        bounds = [self.half(i) & 255 for i in range(a - 8, a - 30, -2)
                  if self.half(i) >> 8 == 0x28 | index]
        if not bounds or not 1 <= bounds[0] <= 100:
            return []
        table = ((a - 2) & ~3) + (adr & 255) * 4
        count = bounds[0]
        self.mark(table, count)
        return [a + 4 + 2 * byte for byte in self.image[table:table + count]]

    def in_code(self, address):
        return (0x20D000 <= address < 0x20DC08 or 0x228000 <= address < 0x235BE8
                or address in self.observed or 0x14600 <= address < 0x146C0
                or 0x14BD18 <= address < 0x14BD54 or 0x14F440 <= address < 0x14FD58
                or 0x262860 <= address < 0x262B00 or 0x14B354 <= address <= 0x14B35E)

    def build(self):
        work = list(self.entries)
        visited = set()
        unresolved = set()
        while work:
            at = work.pop()
            if at in visited or at in self.hand_written:
                continue
            visited.add(at)
            if at < 0 or at + 4 > len(self.image) or not self.in_code(at):
                unresolved.add(at)
                continue
            if 0x14B3A4 <= at < 0x14B4A0:
                continue
            result = self.decode(at)
            if result is None:
                unresolved.add(at)
                continue
            self.translated[at] = result
            work.extend(result[1])
        return unresolved

    def emit(self, output, *, note):
        leaders = self.entries | self.extra_leaders
        for op, targets, following in self.translated.values():
            if "goto" in op or following not in self.translated:
                leaders.update(targets)
        leaders &= self.translated.keys()
        lines = [f'"""Generated by lift.py. {note}"""',
                 "from sgh_x458.runtime.word_ops import add, condition, nz, shift, signed, sub"]
        for start in sorted(leaders):
            lines.extend(("", f"def block_{start:X}(p, r, rd, wr):"))
            address = start
            while True:
                op, targets, following = self.translated[address]
                lines.extend("    " + line for line in self.python_lines(op))
                if "goto" in op:
                    if op.startswith("if "):
                        lines.append(f"    return 0x{following:X}")
                    break
                if following in leaders or following not in self.translated:
                    lines.append(f"    return 0x{following:X}")
                    break
                address = following
        lines.extend(("", "BLOCKS = {"))
        lines.extend(f"    0x{a:X}: block_{a:X}," for a in sorted(leaders))
        lines.append("}")
        output.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")

    @staticmethod
    def python_lines(op):
        op = re.sub(r"(0x[0-9A-F]+)u", r"\1", op).replace("p->", "p.")
        if op.startswith("if "):
            predicate, target = re.fullmatch(r"if \((.*)\) \{ goto L([0-9A-F]+); \}", op).groups()
            return [f"if {predicate}:", f"    return 0x{target}"]
        lines = []
        for statement in op.rstrip(";").split("; "):
            statement = statement.strip()
            if statement == "goto dispatch":
                lines.append("return next_address")
            elif statement.startswith("goto L"):
                lines.append("return 0x" + statement[6:])
            else:
                statement = statement.replace("next = ", "next_address = ")
                cast = re.fullmatch(r"(r\[\d+\] = )\(int32_t\)\(int(8|16)_t\)(rd\(.*\))", statement)
                if cast:
                    left, bits, value = cast.groups()
                    statement = f"{left}signed({value}, {bits}) & 0xFFFFFFFF"
                arithmetic = re.fullmatch(r"(r\[\d+\]) ([+-])= (.*)", statement)
                if arithmetic:
                    dest, operator, value = arithmetic.groups()
                    statement = f"{dest} = ({dest} {operator} ({value})) & 0xFFFFFFFF"
                lines.append(statement)
        return lines

    def write_runtime_data(self, path, *, end_address=None):
        ranges = []
        for address in sorted(self.data):
            if end_address is not None and address >= end_address:
                break
            if ranges and ranges[-1][1] == address:
                ranges[-1][1] += 1
            else:
                ranges.append([address, address + 1])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as output:
            output.write(pack("<I", len(ranges)))
            for start, end in ranges:
                output.write(pack("<II", start, end - start))
                output.write(self.image[start:end])

