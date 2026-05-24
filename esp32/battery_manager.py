import machine
import time
import config

class BatteryManager:
    def __init__(self):
        # Setup ADC for battery voltage measurement
        self.adc = machine.ADC(machine.Pin(config.BATTERY_ADC_PIN))
        # 12-bit resolution (0-4095)
        self.adc.atten(machine.ADC.ATTN_11DB) # 0-3.6V range (with external voltage divider)
        
        # Calibration coefficients
        self.divider_ratio = 2.0  # Assumes 1:1 resistor divider (e.g., 100k / 100k)
        self.v_ref = 3.3
        
    def read_voltage(self):
        """Returns the battery voltage in Volts."""
        raw = self.adc.read()
        # Convert raw ADC reading to voltage on pin
        pin_voltage = (raw / 4095.0) * self.v_ref
        # Calculate battery voltage based on voltage divider
        battery_voltage = pin_voltage * self.divider_ratio
        return battery_voltage

    def get_percentage(self):
        """Returns battery percentage (0-100) based on standard LiPo discharge curve."""
        v = self.read_voltage()
        if v >= 4.2:
            return 100
        elif v <= 3.2:
            return 0
        else:
            # Simple linear approximation for demonstration
            return int((v - 3.2) / (4.2 - 3.2) * 100)
            
    def is_low(self):
        """Returns True if battery is below 15%."""
        return self.get_percentage() < 15
