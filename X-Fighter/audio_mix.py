"""Desktop playback levels for the extracted X-Fighter audio."""

from array import array
from math import cos, sin, sqrt, tau

from handset.desktop import DEFAULT_VOLUME, load_sound_clip
import pygame


PLAYBACK_GAIN = DEFAULT_VOLUME / 100
EFFECT_CUTOFF_HZ = {
    "5A91C0": 760,  # Player hit by an enemy bullet.
    "5A5FDE": 540,  # Enemy explosion.
    "5A7E46": 400,  # Player explosion.
    "5A8489": 600,  # Player missile launch.
    "5AA677": 600,  # Boss missile launch.
}


def high_pass(pcm, rate, channels, cutoff):
    samples = array("h", pcm)
    filtered = [0.0] * len(samples)
    # Butterworth high-pass biquad, normalized to a0 = 1.
    angle = tau * cutoff / rate
    alpha = sin(angle) / sqrt(2)
    c = cos(angle)
    b0 = (1 + c) / (2 * (1 + alpha))
    a1 = -2 * c / (1 + alpha)
    a2 = (1 - alpha) / (1 + alpha)
    for channel in range(channels):
        x1 = x2 = y1 = y2 = 0.0
        for i in range(channel, len(samples), channels):
            x = samples[i]
            y = b0 * (x - 2 * x1 + x2) - a1 * y1 - a2 * y2
            filtered[i] = y
            x2, x1 = x1, x
            y2, y1 = y1, y
    energy = sum(x * x for x in filtered)
    if not energy:
        return pcm
    # Leave room for the sharper transient. The master gain still lowers the output peak.
    peak_limit = min(32767, 1.5 * max(map(abs, samples)))
    peak_gain = peak_limit / max(map(abs, filtered))
    rms_gain = 0.89 * sqrt(sum(x * x for x in samples) / energy)
    gain = min(peak_gain, rms_gain)
    return array("h", (max(-32768, min(32767, round(x * gain))) for x in filtered)).tobytes()


def load_game_clip(path, gain=PLAYBACK_GAIN):
    clip = load_sound_clip(path)
    cutoff = EFFECT_CUTOFF_HZ.get(path.stem)
    if cutoff:
        rate, sample_format, channels = pygame.mixer.get_init()
        if sample_format == -16:
            pcm = high_pass(clip.get_raw(), rate, channels, cutoff)
            clip = pygame.mixer.Sound(buffer=pcm)
    clip.set_volume(gain)
    return clip
