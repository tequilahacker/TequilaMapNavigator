# iphone/tts_handler.py
# Pythonista 3 - Text-to-Speech tiếng Việt + stream audio về ESP32 qua BLE
import time
import binascii

try:
    import speech    # Pythonista native TTS
    import sound     # Pythonista native audio recording/playback
    HAS_PYTHONISTA = True
except ImportError:
    HAS_PYTHONISTA = False
    print("[TTS] Chạy ngoài Pythonista, dùng mock mode.")

class TTSHandler:
    """Chuyển text tiếng Việt thành giọng nói và stream về ESP32."""
    
    SAMPLE_RATE = 16000  # Hz - 16kHz cho quality tốt và bandwidth hợp lý
    
    def __init__(self, ble_handler=None):
        self.ble = ble_handler  # BLEHandler instance để gửi audio
        
    def speak_local(self, text, language="vi-VN", wait=True):
        """Phát âm thanh trực tiếp từ loa iPhone (không cần BLE).
        Dùng cho thông báo cảnh báo quan trọng khi user cầm phone.
        """
        if not HAS_PYTHONISTA:
            print(f"[TTS Local] {text}")
            return
        try:
            speech.say(text, language)
            if wait:
                # Chờ cho TTS xong
                time.sleep(len(text) * 0.08)
        except Exception as e:
            print("[TTS] Lỗi speak_local:", e)
            
    def speak_to_esp32(self, text, language="vi-VN"):
        """Đọc text và stream audio về ESP32 qua BLE.
        
        Flow:
        1. Dùng iOS speech synthesis để generate audio
        2. Encode thành base64
        3. Gửi qua BLE packets
        
        Lưu ý: Pythonista không cho phép capture audio từ TTS trực tiếp.
        Giải pháp: Dùng AVSpeechSynthesizer qua objc_util để render to file.
        """
        if not HAS_PYTHONISTA or not self.ble:
            print(f"[TTS ESP32] {text}")
            return
            
        try:
            from objc_util import ObjCClass, nsurl, on_main_thread
            import os
            
            AVSpeechSynthesizer = ObjCClass('AVSpeechSynthesizer')
            AVSpeechUtterance = ObjCClass('AVSpeechUtterance')
            AVSpeechSynthesisVoice = ObjCClass('AVSpeechSynthesisVoice')
            
            # Output WAV file path
            output_path = '/private/var/mobile/tts_output.wav'
            
            @on_main_thread
            def synthesize():
                utterance = AVSpeechUtterance.speechUtteranceWithString_(text)
                voice = AVSpeechSynthesisVoice.voiceWithLanguage_("vi-VN")
                if voice:
                    utterance.voice = voice
                utterance.rate = 0.48  # Tốc độ nói vừa phải
                utterance.pitchMultiplier = 1.1
                
                synth = AVSpeechSynthesizer.new()
                # Lưu ý: AVSpeechSynthesizer không có writeToURL trong iOS < 16
                # Fallback: Phát qua loa iPhone + gửi text command
                synth.speakUtterance_(utterance)
            
            synthesize()
            
            # Fallback: Gửi text notification về ESP32 thay vì audio
            # ESP32 sẽ hiển thị text lên màn hình
            nav_text = text[:80]  # Giới hạn độ dài
            self.ble.send_text(f"TTS|{nav_text}")
            
        except Exception as e:
            print("[TTS] AVSpeech error:", e)
            # Fallback hoàn toàn: chỉ phát local
            self.speak_local(text, language, wait=False)
            if self.ble:
                self.ble.send_text(f"TTS|{text[:80]}")
                
    def stream_sine_alert(self, freq_hz=880, duration_ms=400):
        """Tạo và stream âm thanh cảnh báo đơn giản (sine wave) về ESP32.
        Dùng cho trường hợp cần alert nhanh không cần TTS.
        """
        if not self.ble:
            return
            
        import math
        sample_rate = 16000
        num_samples = int(sample_rate * duration_ms / 1000)
        buf = bytearray(num_samples * 2)
        
        for i in range(num_samples):
            t = i / sample_rate
            fade = min(t / 0.02, 1.0, (duration_ms/1000 - t) / 0.02)
            sample = int(8000 * fade * math.sin(2 * math.pi * freq_hz * t))
            buf[i*2] = sample & 0xFF
            buf[i*2+1] = (sample >> 8) & 0xFF
        
        # Stream audio về ESP32
        self.ble.send_text("AUDIO_START")
        chunk = 180  # ~MTU safe size
        encoded = binascii.b2a_base64(buf).decode('ascii').strip()
        for i in range(0, len(encoded), chunk):
            self.ble.send_text(encoded[i:i+chunk])
            time.sleep(0.01)
        self.ble.send_text("AUDIO_END")
