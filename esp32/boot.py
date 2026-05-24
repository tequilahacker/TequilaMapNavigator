# boot.py -- run on boot-up
import gc
import machine
import config

# Enable automatic garbage collection
gc.enable()

print("----------------------------------------")
print("VMN-Compact Voice Motorcycle Navigator")
print("Firmware: MicroPython with LVGL bindings")
print("----------------------------------------")

# Initialize display backlight GPIO and turn it on immediately on startup
try:
    backlight = machine.Pin(config.TFT_BL, machine.Pin.OUT)
    backlight.value(1) # Turn backlight ON
    print("[Boot] Display Backlight enabled.")
except Exception as e:
    print("[Boot] Display Backlight pin setup failed:", e)

# Continue to execute main.py automatically
try:
    import main
except Exception as e:
    print("[Boot] Failed to execute main.py:", e)
