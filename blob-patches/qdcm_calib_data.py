#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#

# Expose the calibrated P3 and HDR modes under the sRGB render intents.
#
# The QDCM calibration has separate render intent ids per color gamut: the
# Standard/Default/Enhance color modes are 301/303/307 in sRGB but 302/304/308
# in P3, and HDR content has its own modes (d65_hdr_hbm 257, hdr_d73_hbm 258).
# Stock SurfaceFlinger translates between them. AOSP SurfaceFlinger asks the
# HWC for the same intent in every color mode, so for P3 and HDR content it
# falls back to the uncalibrated COLORIMETRIC intent and the generic d65_hdr
# mode.
#
# Add copies of the P3 SDR and HDR modes under the sRGB intents, so the HWC
# applies the same calibration as stock for every gamut and dynamic range.

import copy
import json
import sys

# sRGB render intent -> (P3 SDR mode, HDR mode) used for it by stock
MODES = {
    301: ('StandardP3', 'd65_hdr_hbm'),
    303: ('DefaultP3', 'hdr_d73_hbm'),
    307: ('EnhanceP3', 'hdr_d73_hbm'),
}


def patch(data):
    calib = json.loads(data)
    panel = next(k for k in calib if k not in ('COPYRIGHT', 'Common', 'Version'))
    modes = calib[panel]
    prefix = next(iter(modes)).split('_')[0]

    patched = {}
    out = {}
    for name, mode in modes.items():
        out[name] = mode
        applicability = mode.get('Applicability', {})
        intent = applicability.get('RenderIntent')
        if (
            intent not in MODES
            or mode.get('DynamicRange') != 'SDR'
            or applicability.get('ColorPrimaries') != 'sRGB'
        ):
            continue
        p3_mode, hdr_mode = MODES[intent]
        for suffix, source in (('_P3', p3_mode), ('_HDR', hdr_mode)):
            new_name = f'{name}{suffix}'
            if new_name not in modes:
                new = copy.deepcopy(modes[f'{prefix}_{source}'])
                new['Applicability']['RenderIntent'] = intent
                new['Applicability']['RenderIntentName'] = new_name.split('_', 1)[1]
                out[new_name] = new
            patched.setdefault(intent, []).append(new_name)

    calib[panel] = out
    return (json.dumps(calib, indent='\t') + '\n').encode(), patched


def blob_fixup(ctx, file, file_path, *args, **kwargs):
    with open(file_path, 'rb') as f:
        data = f.read()
    data, patched = patch(data)
    missing = [intent for intent in MODES if len(patched.get(intent, [])) != 2]
    if missing:
        raise ValueError(f'{file_path}: no sRGB SDR mode for render intents {missing}')
    with open(file_path, 'wb') as f:
        f.write(data)


if __name__ == '__main__':
    for path in sys.argv[1:]:
        with open(path, 'rb') as f:
            data, patched = patch(f.read())
        with open(path, 'wb') as f:
            f.write(data)
        for intent, names in sorted(patched.items()):
            print(f'{path}: {intent} -> {", ".join(names)}')
