import speech_recognition as sr
import io

def test_sr():
    r = sr.Recognizer()
    # Create 1 second of dummy silent PCM data (16000Hz, 16bit, mono)
    pcm_data = b'\x00\x00' * 16000
    
    # Wrap in WAV format
    import struct
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
    
    audio_file = io.BytesIO(wav_data)
    try:
        with sr.AudioFile(audio_file) as source:
            audio = r.record(source)
        print("Successfully recorded audio data into SpeechRecognition library.")
        
        # Test recognition
        print("Sending to recognize_google...")
        text = r.recognize_google(audio, language="vi-VN")
        print("Success! Result:", text)
    except sr.UnknownValueError:
        print("UnknownValueError: Google Speech Recognition could not understand audio (this means API is ALIVE, just no speech detected!)")
    except sr.RequestError as e:
        print("RequestError: Could not request results from Google Speech Recognition service;", e)
    except Exception as e:
        print("Other Exception:", e)

if __name__ == "__main__":
    test_sr()
