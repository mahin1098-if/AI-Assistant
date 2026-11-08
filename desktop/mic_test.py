"""
Microphone test for Joey.
Shows your microphones and a live loudness bar so you can see if Joey can hear you.

Run:  python mic_test.py
"""

import time

import numpy as np
import sounddevice as sd


def usable_mics():
    """Each mic appears several times on Windows (once per audio driver).
    Prefer the 'MME' copies, which are the most compatible."""
    apis = sd.query_hostapis()
    preferred = [i for i, a in enumerate(apis) if a["name"] == "MME"]
    mics = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and (not preferred or d["hostapi"] in preferred):
            if "mapper" not in d["name"].lower():
                mics.append((i, d["name"]))
    return mics


def open_mic(device):
    info = sd.query_devices(device, "input")
    rate = int(info["default_samplerate"])
    channels = max(1, min(int(info["max_input_channels"]), 2))
    return sd.InputStream(device=device, samplerate=rate, channels=channels, dtype="int16"), rate


def live_meter(device=None, seconds=6):
    stream, rate = open_mic(device)
    print(f"\nTesting: {sd.query_devices(device, 'input')['name']}")
    print(f"Talk normally for {seconds} seconds, watch the bar move...\n")
    levels = []
    with stream:
        start = time.time()
        while time.time() - start < seconds:
            block, _ = stream.read(int(rate * 0.1))
            mono = block.astype(np.float32).mean(axis=1)
            level = float(np.sqrt(np.mean(mono ** 2)))
            levels.append(level)
            bar = "#" * min(int(level / 50), 50)
            print(f"\r  level {int(level):5d} |{bar:<50}|", end="", flush=True)
    peak, background = max(levels), float(np.median(levels))
    print(f"\n\n  Loudest you got: {int(peak)}   Room background: {int(background)}")
    if peak < 100:
        print("  -> Almost nothing heard. Try another mic number, or check it isn't muted.")
    elif peak < 300:
        print("  -> Heard you, but quietly. Turn the mic volume up or move closer.")
    else:
        print("  -> This mic works!")


def main():
    mics = usable_mics()
    default_in = sd.default.device[0]
    print("\nMicrophones on this computer:")
    for i, name in mics:
        mark = "  <-- default" if i == default_in else ""
        print(f"  {i}: {name}{mark}")
    print()

    choice = input("Press Enter to test the default mic, or type a number to test another: ").strip()
    device = int(choice) if choice.isdigit() else None
    try:
        live_meter(device)
    except Exception as e:
        print(f"\nCouldn't open that microphone: {e}")
        print("Try a different number from the list.")
        return
    if device is not None:
        print(f"\nIf this one worked, open joey_voice.py in Notepad and set:  MIC_DEVICE = {device}")


if __name__ == "__main__":
    main()
