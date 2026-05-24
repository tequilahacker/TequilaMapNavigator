# esp32/greeting.py
# Boot animation + welcome sound player for Tequila Navigator
import lvgl as lv
import time
import config

class GreetingScreen:
    """Hiển thị màn hình chào và phát âm thanh khi khởi động."""
    
    def __init__(self, audio_out=None):
        """
        audio_out: machine.I2S object từ VoiceHandler, hoặc None nếu không có loa.
        """
        self.audio_out = audio_out
        self._show_boot_screen()
        
    def _show_boot_screen(self):
        """Vẽ màn hình khởi động với logo và tên thiết bị."""
        # Tạo màn hình đen chuyên nghiệp
        self.scr = lv.obj()
        self.scr.set_style_bg_color(lv.color_make(15, 15, 25), 0)  # Xanh đen sâu
        lv.scr_load(self.scr)
        
        # Logo circle (giả lập icon bản đồ)
        logo_circle = lv.obj(self.scr)
        logo_circle.set_size(80, 80)
        logo_circle.align(lv.ALIGN.CENTER, 0, -50)
        logo_circle.set_style_bg_color(lv.color_make(0, 128, 255), 0)
        logo_circle.set_style_radius(lv.RADIUS_CIRCLE, 0)
        logo_circle.set_style_border_width(3, 0)
        logo_circle.set_style_border_color(lv.color_make(0, 220, 255), 0)
        
        # Icon "T" trong logo
        logo_text = lv.label(logo_circle)
        logo_text.set_text("T")
        logo_text.align(lv.ALIGN.CENTER, 0, 0)
        logo_text.set_style_text_color(lv.color_make(255, 255, 255), 0)
        
        # Tên thiết bị
        title = lv.label(self.scr)
        title.set_text("TEQUILA")
        title.align(lv.ALIGN.CENTER, 0, 20)
        title.set_style_text_color(lv.color_make(0, 200, 255), 0)
        
        # Subtitle
        subtitle = lv.label(self.scr)
        subtitle.set_text("Motorcycle Navigator")
        subtitle.align(lv.ALIGN.CENTER, 0, 48)
        subtitle.set_style_text_color(lv.color_make(180, 180, 180), 0)
        
        # Loading bar
        self.progress_bar = lv.bar(self.scr)
        self.progress_bar.set_size(config.DISPLAY_WIDTH - 40, 6)
        self.progress_bar.align(lv.ALIGN.CENTER, 0, 100)
        self.progress_bar.set_range(0, 100)
        self.progress_bar.set_value(0, lv.ANIM.OFF)
        self.progress_bar.set_style_bg_color(lv.color_make(40, 40, 60), 0)
        
        bar_style = lv.style_t()
        bar_style.init()
        bar_style.set_bg_color(lv.color_make(0, 180, 255))
        self.progress_bar.add_style(bar_style, lv.PART.INDICATOR)
        
        # Status text
        self.status_label = lv.label(self.scr)
        self.status_label.set_text("Đang khởi động...")
        self.status_label.align(lv.ALIGN.CENTER, 0, 125)
        self.status_label.set_style_text_color(lv.color_make(120, 120, 140), 0)
        
        lv.task_handler()
        
    def animate_loading(self, progress_pct, status_text=""):
        """Cập nhật thanh tiến trình boot."""
        self.progress_bar.set_value(progress_pct, lv.ANIM.ON)
        if status_text:
            self.status_label.set_text(status_text)
        lv.task_handler()
        
    def play_greeting_wav(self):
        """Phát file WAV 'Xin Chào' từ flash hoặc dùng sine-wave test tone.
        
        Trong production, thay thế bằng file greeting.wav được mã hóa
        dưới dạng bytearray và lưu trong firmware hoặc flash filesystem.
        """
        if not self.audio_out:
            print("[Greeting] Không có I2S speaker, bỏ qua âm thanh.")
            return
        
        # Test tone: sine wave 440Hz trong 0.5 giây để xác nhận loa hoạt động
        # Trong production: đọc file greeting.wav từ flash
        try:
            import math
            sample_rate = 16000
            freq = 880  # Hz - âm thanh chào
            duration = 0.4  # giây
            num_samples = int(sample_rate * duration)
            
            # Tạo sine wave buffer 16-bit
            buf = bytearray(num_samples * 2)
            for i in range(num_samples):
                # Fade in/out để tránh click noise
                t = i / sample_rate
                envelope = min(t / 0.05, 1.0, (duration - t) / 0.05)
                sample = int(12000 * envelope * math.sin(2 * math.pi * freq * t))
                # Little-endian 16-bit signed
                buf[i*2] = sample & 0xFF
                buf[i*2+1] = (sample >> 8) & 0xFF
                
            self.audio_out.write(buf)
            
            # Tone thứ hai (chào hỏi 2-note)
            time.sleep_ms(100)
            buf2 = bytearray(num_samples * 2)
            freq2 = 1100
            for i in range(num_samples):
                t = i / sample_rate
                envelope = min(t / 0.05, 1.0, (duration - t) / 0.05)
                sample = int(10000 * envelope * math.sin(2 * math.pi * freq2 * t))
                buf2[i*2] = sample & 0xFF
                buf2[i*2+1] = (sample >> 8) & 0xFF
            self.audio_out.write(buf2)
            
        except Exception as e:
            print("[Greeting] Lỗi phát âm thanh:", e)

    def run_boot_sequence(self, journey_state_manager, audio_out=None):
        """Chạy toàn bộ trình tự khởi động.
        
        Trả về:
          'resume' nếu có hành trình đang dở cần tiếp tục
          'ready'  nếu sẵn sàng nhận lệnh mới
        """
        self.audio_out = audio_out
        
        # Bước 1: Khởi động hệ thống
        self.animate_loading(10, "Khởi động hệ thống...")
        time.sleep_ms(200)
        
        # Bước 2: Phát âm thanh chào
        self.animate_loading(30, "Xin chào!")
        self.play_greeting_wav()
        
        # Bước 3: Kiểm tra hành trình đang dở
        self.animate_loading(60, "Kiểm tra hành trình...")
        time.sleep_ms(200)
        
        has_journey = False
        try:
            has_journey = journey_state_manager.has_saved_journey()
        except Exception:
            pass
            
        # Bước 4: Kết nối BLE
        self.animate_loading(85, "Chờ kết nối iPhone...")
        time.sleep_ms(300)
        
        # Bước 5: Hoàn thành
        self.animate_loading(100, "Sẵn sàng!")
        time.sleep_ms(400)
        
        if has_journey:
            self.status_label.set_text("Tiếp tục hành trình cũ...")
            self.status_label.set_style_text_color(lv.color_make(46, 204, 113), 0)
            lv.task_handler()
            time.sleep_ms(800)
            return 'resume'
        else:
            return 'ready'
