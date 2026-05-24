import bluetooth
import config
import time

class BLEHandler:
    def __init__(self, on_receive_callback=None, on_connect_callback=None, on_disconnect_callback=None):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)
        self.on_receive = on_receive_callback
        self.on_connect = on_connect_callback
        self.on_disconnect = on_disconnect_callback
        
        self.service_uuid = bluetooth.UUID(config.BLE_SERVICE_UUID)
        self.tx_uuid = bluetooth.UUID(config.BLE_TX_CHAR_UUID)
        self.rx_uuid = bluetooth.UUID(config.BLE_RX_CHAR_UUID)
        
        # Setup services
        services = (
            (self.service_uuid, (
                (self.tx_uuid, bluetooth.FLAG_NOTIFY),
                (self.rx_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE),
            )),
        )
        ((self.tx_handle, self.rx_handle),) = self.ble.gatts_register_services(services)
        
        self.connections = set()
        self.mtu = 23  # Default BLE MTU size
        self.start_advertising()
        
    def _irq(self, event, data):
        # 1: _IRQ_CENTRAL_CONNECT
        if event == 1:
            conn_handle, _, _ = data
            self.connections.add(conn_handle)
            print("[BLE] Central connected, handle:", conn_handle)
            if self.on_connect:
                self.on_connect()
                
        # 2: _IRQ_CENTRAL_DISCONNECT
        elif event == 2:
            conn_handle, _, _ = data
            if conn_handle in self.connections:
                self.connections.remove(conn_handle)
            print("[BLE] Central disconnected, handle:", conn_handle)
            if self.on_disconnect:
                self.on_disconnect()
            self.start_advertising()
            
        # 3: _IRQ_GATTS_WRITE
        elif event == 3:
            conn_handle, value_handle = data
            if value_handle == self.rx_handle:
                payload = self.ble.gatts_read(self.rx_handle)
                if self.on_receive:
                    self.on_receive(payload)
                    
        # 21: _IRQ_MTU_EXCHANGE
        elif event == 21:
            conn_handle, mtu = data
            self.mtu = mtu
            print("[BLE] MTU negotiated to:", mtu)

    def start_advertising(self):
        name = config.BLE_DEVICE_NAME
        # Construct raw advertising packet
        payload = bytearray(b'\x02\x01\x06') # General discoverable, BR/EDR not supported
        payload.append(len(name) + 1)
        payload.append(0x09) # Complete Local Name
        payload.extend(name.encode('utf-8'))
        
        # Also include Service UUID in advertising data
        payload.extend(b'\x11\x07') # 17 bytes: 1 byte length (17), 1 byte type (0x07 for complete list of 128-bit Service UUIDs)
        # Convert UUID to little-endian bytes
        uuid_bytes = bytes(reversed(self.service_uuid.as_bytes()))
        payload.extend(uuid_bytes)
        
        self.ble.gap_advertise(100, payload)
        print("[BLE] Advertising started as:", name)
        
    def send(self, data):
        """Sends data back to iPhone central. Splits into chunks if needed based on MTU."""
        if not self.connections:
            return False
        
        # Max payload is MTU - 3 bytes header
        chunk_size = self.mtu - 3
        total_len = len(data)
        
        for conn_handle in self.connections:
            for offset in range(0, total_len, chunk_size):
                chunk = data[offset:offset + chunk_size]
                try:
                    self.ble.gatts_notify(conn_handle, self.tx_handle, chunk)
                    # Give a tiny breathing room for the BLE stack if we are sending multiple chunks
                    if total_len > chunk_size:
                        time.sleep_ms(15)
                except Exception as e:
                    print("[BLE] Error sending notify chunk:", e)
                    return False
        return True

    def is_connected(self):
        return len(self.connections) > 0

