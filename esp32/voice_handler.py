# esp32/voice_handler.py
# MicroPython - Quản lý Loa (MAX98357A) và Mic (INMP441) cục bộ trên ESP32
import machine
import config
import time
import socket

class VoiceHandler:
    """Quản lý I2S Speaker và Microphone cục bộ trên ESP32."""
    
    def __init__(self, i2s_mic_sck=None, i2s_mic_ws=None, i2s_mic_sd=None,
                 i2s_spk_sck=None, i2s_spk_ws=None, i2s_spk_sd=None):
        
        # 1. Khởi tạo loa I2S Speaker (MAX98357)
        spk_sck = i2s_spk_sck if i2s_spk_sck is not None else config.SPK_SCK
        spk_ws  = i2s_spk_ws  if i2s_spk_ws  is not None else config.SPK_WS
        spk_sd  = i2s_spk_sd  if i2s_spk_sd  is not None else config.SPK_SD
        
        try:
            self.audio_out = machine.I2S(
                0,
                sck=machine.Pin(spk_sck),
                ws=machine.Pin(spk_ws),
                sd=machine.Pin(spk_sd),
                mode=machine.I2S.TX,
                bits=16,
                format=machine.I2S.MONO,
                rate=16000,   # Tần số 16kHz chuẩn cho đàm thoại AI
                ibuf=20480    # Buffer 20KB giúp tiếng loa mịn màng
            )
            print("[Voice] Loa I2S (MAX98357) khởi tạo thành công.")
        except Exception as e:
            self.audio_out = None
            print("[Voice] ❌ Lỗi khởi tạo loa I2S:", e)

        # 2. Khởi tạo Mic I2S (INMP441)
        mic_sck = i2s_mic_sck if i2s_mic_sck is not None else config.MIC_SCK
        mic_ws  = i2s_mic_ws  if i2s_mic_ws  is not None else config.MIC_WS
        mic_sd  = i2s_mic_sd  if i2s_mic_sd  is not None else config.MIC_SD
        
        try:
            self.audio_in = machine.I2S(
                1,
                sck=machine.Pin(mic_sck),
                ws=machine.Pin(mic_ws),
                sd=machine.Pin(mic_sd),
                mode=machine.I2S.RX,
                bits=16,
                format=machine.I2S.MONO,
                rate=16000,
                ibuf=10240
            )
            print("[Voice] Microphone I2S (INMP441) khởi tạo thành công.")
        except Exception as e:
            self.audio_in = None
            print("[Voice] ❌ Lỗi khởi tạo Mic I2S:", e)

    def play_beep(self, freq=1000, duration_ms=200):
        """Phát tiếng bíp bíp cảnh báo khẩn cấp bằng cách tạo sóng hình sin thô."""
        if not self.audio_out:
            return
        try:
            import math
            sample_rate = 16000
            num_samples = int(sample_rate * duration_ms / 1000)
            buf = bytearray(num_samples * 2)
            for i in range(num_samples):
                t = i / sample_rate
                # Fade in / Fade out 10ms để triệt tiêu tiếng bụp phần cứng
                fade = min(t / 0.01, 1.0, (duration_ms/1000 - t) / 0.01)
                sample = int(10000 * fade * math.sin(2 * math.pi * freq * t))
                buf[i*2] = sample & 0xFF
                buf[i*2+1] = (sample >> 8) & 0xFF
            self.audio_out.write(buf)
        except Exception as e:
            print("[Voice] Lỗi phát tiếng bíp:", e)

    def detect_vad_trigger(self, threshold_db=2500, check_duration_ms=200):
        """Phát hiện kích hoạt giọng nói (VAD) đơn giản bằng cách đo cường độ biên độ trung bình."""
        if not self.audio_in:
            return False
            
        chunk_size = 512
        buf = bytearray(chunk_size)
        total_amplitude = 0
        samples_count = 0
        
        # Đọc thử trong check_duration_ms
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < check_duration_ms:
            bytes_read = self.audio_in.readinto(buf)
            if bytes_read > 0:
                # Đo trị tuyệt đối biên độ 16-bit
                for i in range(0, bytes_read, 2):
                    val = buf[i] | (buf[i+1] << 8)
                    # Convert to signed 16-bit
                    if val & 0x8000:
                        val -= 65536
                    total_amplitude += abs(val)
                    samples_count += 1
        
        if samples_count > 0:
            avg = total_amplitude / samples_count
            # Nếu âm lượng trung bình vượt ngưỡng quy định, kích hoạt ghi âm!
            if avg > threshold_db:
                print(f"[VAD] Kích hoạt phát hiện tiếng nói! Biên độ: {avg:.1f} > {threshold_db}")
                return True
        return False

    def record_audio(self, duration_sec=4, update_ui_cb=None):
        """Ghi âm từ Mic I2S vào mảng bytearray trong RAM (Sắp xếp 16kHz, 16-bit Mono).
        4 giây ≈ 128KB, hoàn toàn nằm trong mức an toàn của SRAM ESP32-S3.
        """
        if not self.audio_in:
            print("[Voice] ❌ Không có Mic, bỏ qua ghi âm.")
            return None

        chunk_size = 1024
        buf = bytearray(chunk_size)
        
        # 16kHz * 2 bytes/sample (16-bit) = 32000 bytes/giây
        total_bytes = 16000 * 2 * duration_sec
        audio_data = bytearray(total_bytes)
        
        print(f"[Voice] Bắt đầu ghi âm cục bộ {duration_sec} giây...")
        self.play_beep(1200, 100)  # Bíp ngắn báo hiệu bắt đầu nói
        
        bytes_written = 0
        start_ticks = time.ticks_ms()
        
        # Xóa sạch đệm mic cũ
        while self.audio_in.readinto(buf) > 0:
            pass

        while bytes_written < total_bytes:
            bytes_read = self.audio_in.readinto(buf)
            if bytes_read > 0:
                # Copy dữ liệu vào đệm chính
                audio_data[bytes_written:bytes_written+bytes_read] = buf[:bytes_read]
                bytes_written += bytes_read
                
            if update_ui_cb:
                update_ui_cb(bytes_written / total_bytes)
                
            # Tránh nghẽn scheduler
            time.sleep_ms(2)
            
        print("[Voice] Ghi âm thành công!")
        self.play_beep(880, 100)  # Bíp báo hiệu nói xong
        return audio_data

    def post_audio_to_iphone(self, server_ip, audio_data):
        """Truyền trực tiếp đệm âm thanh PCM nhị phân thô lên Server (Local hoặc Cloud) qua socket HTTP/HTTPS POST."""
        if not audio_data:
            return False
            
        # Kiểm tra chế độ Cloud hay Local
        if config.USE_CLOUD_SERVER:
            host = config.CLOUD_SERVER_HOST
            port = config.CLOUD_SERVER_PORT
            use_ssl = config.CLOUD_SERVER_SSL
            print(f"[Voice] Đang kết nối lên CLOUD {host}:{port} ({'HTTPS' if use_ssl else 'HTTP'}) để đẩy giọng nói...")
        else:
            host = server_ip
            port = 8080
            use_ssl = False
            print(f"[Voice] Đang kết nối lên LOCAL {host}:{port} để đẩy giọng nói...")
            
        try:
            # Phân giải IP và thiết lập kết nối TCP thuần để tối ưu bộ nhớ
            addr = socket.getaddrinfo(host, port)[0][-1]
            s = socket.socket()
            s.settimeout(10.0) # Tăng timeout lên 10s cho Cloud
            s.connect(addr)
            
            # Nếu dùng HTTPS, bọc socket với SSL
            if use_ssl:
                try:
                    import ussl
                    s = ussl.wrap_socket(s, server_hostname=host)
                    print("[Voice] Thiết lập kênh truyền SSL/TLS bảo mật thành công.")
                except Exception as err:
                    try:
                        import ssl
                        s = ssl.wrap_socket(s, server_hostname=host)
                        print("[Voice] Thiết lập kênh truyền SSL bảo mật thành công.")
                    except Exception as err2:
                        print("[Voice] ❌ Không bọc được SSL socket:", err2)
            
            # Khởi tạo HTTP POST Request Headers
            headers = (
                f"POST /api/voice-command HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Content-Type: application/octet-stream\r\n"
                f"Content-Length: {len(audio_data)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode()
            
            s.send(headers)
            
            # Truyền tải dữ liệu âm thanh theo từng chunk nhỏ 1024 bytes
            chunk_size = 1024
            for i in range(0, len(audio_data), chunk_size):
                s.send(audio_data[i:i+chunk_size])
                
            # Đón nhận phản hồi từ Server
            response = s.recv(512)
            s.close()
            resp_str = response.decode('utf-8', 'ignore')
            print("[Voice] ✅ Đẩy âm thanh thành công! Phản hồi từ Server:", resp_str.split("\r\n")[0])
            return True
        except Exception as e:
            print("[Voice] ❌ Lỗi truyền tải âm thanh qua HTTP/HTTPS:", e)
            return False

