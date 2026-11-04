#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

# Keep Dolby Vision and 120 fps video mutually exclusive.
#
# camera_unit_feature_config.protobuf is a string pool (field 1) plus a tree of
# features that refer to pool entries by index. A feature has its key in field 2
# and one rule per value in field 8; a rule holds the value in field 1 and its
# constraints in field 2, each constraint being {1: key, 2: from, 3: to}.
# Stock already uses {key_video_dolby, on, off} for 720p. The HAL produces no
# video frames for Dolby Vision at 120 fps, so:
#  - switching to 120 fps turns Dolby Vision off, and
#  - turning Dolby Vision on drops 120 fps to 60 fps.

import sys

# (feature key, feature value, constraint added to that value's rule)
RULES = [
    ('pref_video_fps_key', '120', ('key_video_dolby', 'on', 'off')),
    ('key_video_dolby', 'on', ('pref_video_fps_key', '120', '60')),
]


def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def _enc_varint(v):
    out = bytearray()
    while True:
        c = v & 0x7F
        v >>= 7
        if v:
            out.append(c | 0x80)
        else:
            out.append(c)
            return bytes(out)


def _parse(b):
    i, items = 0, []
    while i < len(b):
        key, i = _varint(b, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(b, i)
        elif wire == 2:
            n, i = _varint(b, i)
            value = b[i : i + n]
            i += n
        elif wire == 5:
            value = b[i : i + 4]
            i += 4
        elif wire == 1:
            value = b[i : i + 8]
            i += 8
        else:
            raise ValueError(f'unsupported wire type {wire}')
        items.append([field, wire, value])
    return items


def _serialize(items):
    out = bytearray()
    for field, wire, value in items:
        out += _enc_varint(field << 3 | wire)
        if wire == 0:
            out += _enc_varint(value)
        elif wire == 2:
            out += _enc_varint(len(value)) + value
        else:
            out += value
    return bytes(out)


def _try_parse(b):
    try:
        return _parse(b)
    except (ValueError, IndexError):
        return None


def _constraints(rule_constraints):
    return {
        tuple(x for _, wx, x in _parse(c)[:3] if wx == 0)
        for f, w, c in _parse(rule_constraints)
        if f == 1 and w == 2
    }


def patch(data):
    top = _parse(data)
    if _serialize(top) != data:
        raise ValueError('protobuf does not round-trip, refusing to patch')

    pool = [v.decode() for f, w, v in top if f == 1 and w == 2]
    index = {s: i for i, s in enumerate(pool)}
    rules = {}
    for key, value, constraint in RULES:
        rules.setdefault((index[key], index[value]), []).append(
            tuple(index[s] for s in constraint)
        )
    feature_keys = {k for k, _ in rules}
    patched = {rule: 0 for rule in RULES}

    def patch_rule(feature_key, rule):
        values = [v for f, w, v in rule if f == 1 and w == 0]
        wanted = rules.get((feature_key, values[0])) if values else None
        if not wanted:
            return False
        for item in rule:
            if item[0] != 2 or item[1] != 2:
                continue
            existing = _constraints(item[2])
            items = _parse(item[2])
            added = False
            for constraint in wanted:
                if constraint in existing:
                    continue
                entry = _serialize([[i + 1, 0, x] for i, x in enumerate(constraint)])
                items.append([1, 2, entry])
                for r in RULES:
                    if (index[r[0]], index[r[1]]) == (feature_key, values[0]) and tuple(
                        index[s] for s in r[2]
                    ) == constraint:
                        patched[r] += 1
                added = True
            if added:
                item[2] = _serialize(items)
            return added
        return False

    def walk(b):
        items = _try_parse(b)
        if items is None:
            return b, False
        changed = False
        keys = [v for f, w, v in items if f == 2 and w == 0]
        is_feature = keys and any(f == 8 and w == 2 for f, w, _ in items)
        if is_feature:
            if keys[0] in feature_keys:
                for item in items:
                    if item[0] == 8 and item[1] == 2:
                        rule = _parse(item[2])
                        if patch_rule(keys[0], rule):
                            item[2] = _serialize(rule)
                            changed = True
            return (_serialize(items), True) if changed else (b, False)
        for item in items:
            if item[1] == 2 and len(item[2]) > 1:
                sub, c = walk(item[2])
                if c:
                    item[2] = sub
                    changed = True
        return (_serialize(items), True) if changed else (b, False)

    for item in top:
        if item[0] != 1 and item[1] == 2:
            sub, c = walk(item[2])
            if c:
                item[2] = sub
    return _serialize(top), patched


def blob_fixup(ctx, file, file_path, *args, **kwargs):
    with open(file_path, 'rb') as f:
        data = f.read()
    data, patched = patch(data)
    missing = [rule for rule, n in patched.items() if not n]
    if missing:
        raise ValueError(f'{file_path}: no rule to patch for {missing}')
    with open(file_path, 'wb') as f:
        f.write(data)


if __name__ == '__main__':
    for path in sys.argv[1:]:
        with open(path, 'rb') as f:
            data, patched = patch(f.read())
        with open(path, 'wb') as f:
            f.write(data)
        for (key, value, constraint), n in patched.items():
            print(f'{path}: {key}={value} += {constraint}: {n}')
