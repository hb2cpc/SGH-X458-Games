"""Encode the extracted handset sounds for Android's single audio channel."""

import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from sgh_x458.x_fighter.audio_mix import EFFECT_CUTOFF_HZ, high_pass


def encode(source, target, cutoff):
    with wave.open(str(source), "rb") as sound:
        params = sound.getparams()
        if params.sampwidth != 2:
            raise ValueError(f"Expected signed 16-bit audio: {source}")
        pcm = sound.readframes(params.nframes)
    if cutoff is not None:
        pcm = high_pass(pcm, params.framerate, params.nchannels, cutoff)
    samples = array("h", pcm)
    channels = params.nchannels
    if channels == 2 and samples[::2] == samples[1::2]:
        # Most handset sounds carry the same signal twice; one channel is all there is to keep.
        samples, channels = samples[::2], 1
    with wave.open(str(target.with_suffix(".wav")), "wb") as cleanup:
        cleanup.setparams(params._replace(nchannels=channels, nframes=len(samples) // channels))
        cleanup.writeframes(samples.tobytes())
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(target.with_suffix(".wav")),
                    "-c:a", "libvorbis", "-q:a", "4", "-map_metadata", "-1", str(target)], check=True)


def main(destination, games):
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        for game in games:
            wavs = sorted((ROOT / "src" / "sgh_x458" / game / "assets/audio/firmware_wav").glob("*.wav"))
            if not wavs:
                raise FileNotFoundError(f"No firmware WAVs found for {game}")
            output = destination / game
            output.mkdir(parents=True, exist_ok=True)
            for source in wavs:
                target = Path(scratch) / f"{source.stem}.ogg"
                cutoff = EFFECT_CUTOFF_HZ.get(source.stem) if game == "x_fighter" else None
                encode(source, target, cutoff)
                shutil.move(str(target), output / target.name)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
