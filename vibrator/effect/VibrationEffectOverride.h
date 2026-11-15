/*
 * SPDX-FileCopyrightText: The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */

/*
 * Effect tables of the OPLUS vibrator HAL (hardware/oplus aidl/vibrator/qti/effect), picked up
 * through the INCLUDE_DIR soong config. They replace the built-in tables and the JSON library.
 *
 * effects:    AOSP Effect id -> waveform, TEXTURE_TICK is id 21.
 * primitives: AOSP CompositePrimitive id -> waveform.
 *
 * Both are generated from the stock vibrator library, see generate_effects.py.
 */

#pragma once

#include "standard_effect.h"
#include "primitive_effect.h"
