import requests
import json
import struct

def test_stt():
    # Create 1 second of dummy silent PCM data (16000Hz, 16bit, mono)
    pcm_data = b'\x00\x00' * 16000
    
    sample_rate = 16000
    bits = 16
    channels = 1
    
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        len(pcm_data) + 36,
        b'WAVE',
        b'fmt ',
        16, 1, channels,
        sample_rate,
        sample_rate * channels * bits // 8,
        channels * bits // 8,
        bits,
        b'data',
        len(pcm_data)
    )
    wav_data = header + pcm_data
    
    url = "https://www.google.com/speech-api/v1/recognize?client=chromium&lang=vi-VN"
    headers = {"Content-Type": "audio/x-wav; rate=16000"}
    try:
        r = requests.post(url, data=wav_data, headers=headers, timeout=8)
        print("Status code:", r.status_code)
        print("Response text:", r.text)
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    test_stt()
