"""Fixed-width arithmetic used by the extracted control flow."""

MASK = 0xFFFFFFFF


def signed(value, bits=32):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def nz(p, value):
    value &= MASK
    p.n = value >> 31
    p.z = value == 0
    return value


def add(p, x, y, carry):
    total = x + y + carry
    p.c = total >> 32
    p.v = ((x ^ total) & (y ^ total)) >> 31 & 1
    return nz(p, total)


def sub(p, x, y, carry):
    return add(p, x, y ^ MASK, carry)


def shift(p, value, amount, mode):
    if not amount:
        return nz(p, value)
    if mode == 0:
        p.c = amount <= 32 and (value >> (32 - amount)) & 1
        result = value << amount if amount < 32 else 0
    elif mode == 1:
        p.c = amount <= 32 and (value >> (amount - 1)) & 1
        result = value >> amount if amount < 32 else 0
    elif mode == 2:
        amount = min(amount, 32)
        p.c = (value >> (amount - 1)) & 1
        result = signed(value) >> amount
    else:
        amount &= 31
        result = (value >> amount) | (value << (32 - amount)) if amount else value
        p.c = (result >> 31) & 1
    return nz(p, result)


def condition(p, code):
    if code == 0:
        return p.z
    if code == 1:
        return not p.z
    if code == 2:
        return p.c
    if code == 3:
        return not p.c
    if code == 4:
        return p.n
    if code == 5:
        return not p.n
    if code == 6:
        return p.v
    if code == 7:
        return not p.v
    if code == 8:
        return p.c and not p.z
    if code == 9:
        return not p.c or p.z
    if code == 10:
        return p.n == p.v
    if code == 11:
        return p.n != p.v
    if code == 12:
        return not p.z and p.n == p.v
    return p.z or p.n != p.v


# Helpers for the firmware's Thumb-to-ARM integer library stubs.
def divide_unsigned_words(game):
    r = game.r
    r[0], r[1] = divmod(r[1], r[0])


def divide_long(game):
    r = game.r
    numerator = r[0] | (r[1] << 32)
    denominator = r[2] | (r[3] << 32)
    quotient, remainder = divmod(numerator, denominator) if denominator else (0, numerator)
    r[:4] = quotient & MASK, quotient >> 32, remainder & MASK, remainder >> 32


def unequal_long(game):
    r = game.r
    if sub(game, r[0], r[2], 1) == 0:
        sub(game, r[1], r[3], 1)
    r[0] = int(not game.z)


def shift_long(game):
    r = game.r
    difference = sub(game, r[2], 32, 1)
    r[3] = (-difference & MASK) if game.n else difference
    low, high = r[:2]
    if game.n:
        r[0] = ((low >> (r[2] & 255)) | (high << (r[3] & 255))) & MASK
        r[1] = high >> (r[2] & 255)
    else:
        r[0] = high >> (r[3] & 255)
        r[1] = 0


def negate_long(game):
    r = game.r
    r[0] = sub(game, 0, r[0], 1)
    r[1] = (-r[1] - (not game.c)) & MASK


def less_long(game):
    r = game.r
    sub(game, r[1], r[3], 1)
    if game.z:
        sub(game, r[0], r[2], 1)
        r[0] = int(not game.c)
    else:
        r[0] = int(game.n != game.v)


MATH_RULES = {
    0x14B36C: divide_unsigned_words,
    0x14CBE4: divide_long,
    0x14CC74: unequal_long,
    0x14CFB4: shift_long,
    0x14D0FC: negate_long,
    0x14D164: less_long,
}
