# esp32/ble_haystack.py
# OpenHaystack BLE Advertising cho ESP32
# Cho phep thiet bi Tequila Map xuat hien trong app Tim (Find My) cua iPhone
#
# Nguon goc: OpenHaystack (seemoo-lab) - reverse-engineer giao thuc BLE cua Apple
# Cach hoat dong:
#   1. ESP32 phat BLE advertisement theo dung format Apple Find My
#   2. iPhone gan do (Bluetooth bat) tu dong pick up va gui len Apple server
#   3. Server Render query Apple Find My de lay GPS cua thiet bi
#
# KEY PAIR: Moi thiet bi can 1 cap khoa EC P-224 duy nhat
# Khoa nay duoc tao 1 lan va luu vao config.py

import bluetooth
import struct
import time

# ==========================================
# DEFAULT KEY - thay bang khoa cua ban sau khi gen
# (28 bytes = 224-bit public key compressed, bo 2 byte dau 0x02)
# ==========================================
DEFAULT_PUBLIC_KEY_BYTES = bytes([
    0xDE, 0xAD, 0xBE, 0xEF, 0xCA, 0xFE, 0x01, 0x02,
    0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A,
    0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12,
    0x13, 0x14, 0x15, 0x16
])


class HaystackAdvertiser:
    """Phat BLE advertisement theo chuan Apple Find My (OpenHaystack).
    
    Format packet:
    [0x02, 0x01, 0x06]             - Flags (LE General Discoverable)
    [0x1B, 0xFF, 0x4C, 0x00]      - Manufacturer Data, Apple Inc.
    [0x12, 0x19]                   - FindMy type (0x12), length (0x19=25)
    [0x00]                         - Status byte
    [22 bytes public key payload]  - Tu byte 2 den byte 23 cua pub key
    [key_byte_0 >> 6]              - Last 2 bits cua byte 0 lam hint
    [0x00, 0x00]                   - Reserved
    """

    def __init__(self, public_key_bytes=None):
        self._key = public_key_bytes or DEFAULT_PUBLIC_KEY_BYTES
        self._ble = None
        self._adv_active = False
        self._interval_ms = 500  # 500ms giua cac lan phat

    def _build_advertisement(self):
        """Xay dung BLE advertisement payload theo chuan OpenHaystack."""
        key = self._key

        # 22 bytes payload tu vi tri 2 tro di
        key_payload = key[2:24]  # 22 bytes
        hint = (key[0] >> 6) & 0x03  # 2 bit cao nhat

        # Apple manufacturer data (FindMy frame)
        apple_data = bytes([
            0x12,        # Subtype: FindMy
            0x19,        # Length: 25 bytes tiep theo
            0x00,        # Status
        ]) + key_payload + bytes([hint]) + bytes([key[1] >> 6, 0x00])

        # Full manufacturer data voi Apple company ID (0x004C)
        mfr_data = bytes([0x4C, 0x00]) + apple_data

        return mfr_data

    def start(self):
        """Khoi dong BLE advertising."""
        try:
            self._ble = bluetooth.BLE()
            self._ble.active(True)
            time.sleep_ms(100)

            adv_payload = self._build_advertisement()

            # Set MAC address ngau nhien (rotates theo Apple spec)
            # ESP32 se tu dong xoay MAC theo interval

            # BLE advertisement voi manufacturer specific data
            # Flag: LE General Discoverable + BR/EDR Not Supported
            flags = bytes([0x02, 0x01, 0x06])
            mfr  = bytes([len(adv_payload) + 1, 0xFF]) + adv_payload

            payload = flags + mfr

            # Phat advertisement non-connectable (Apple Find My khong can connect)
            self._ble.gap_advertise(
                self._interval_ms * 1000,  # microseconds
                adv_data=payload,
                connectable=False
            )
            self._adv_active = True
            print("[Haystack] BLE advertising bat dau! Thiet bi se xuat hien trong app Tim.")
            print("[Haystack] Key hint:", hex(self._key[0] >> 6))
            return True
        except Exception as e:
            print("[Haystack] Loi khoi dong BLE:", e)
            return False

    def stop(self):
        """Dung BLE advertising."""
        try:
            if self._ble:
                self._ble.gap_advertise(None)  # None = dung
                self._adv_active = False
                print("[Haystack] Da dung BLE advertising.")
        except Exception as e:
            print("[Haystack] Loi dung BLE:", e)

    @property
    def is_active(self):
        return self._adv_active

    def set_key(self, public_key_bytes):
        """Cap nhat public key (khi co rolling key)."""
        self._key = public_key_bytes
        if self._adv_active:
            # Restart advertising voi key moi
            self.stop()
            time.sleep_ms(50)
            self.start()


def gen_key_info():
    """Thong tin de tao key pair tren server.
    
    Key pair EC P-224 duoc tao tren server (Render) bang Python:
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ec.generate_private_key(ec.SECP224R1())
        pub = key.public_key().public_bytes(Encoding.X962, PublicFormat.CompressedPoint)
        # pub = 29 bytes (0x02/0x03 + 28 bytes)
        # Luu private key de doc Find My reports
        # Gui 28 bytes public key (bo byte dau) vao config.py cua ESP32
    """
    print("[Haystack] De tao key pair:")
    print("  1. Vao https://tequilamap.onrender.com/api/gen-findmy-key")
    print("  2. Copy public_key_bytes vao config.py -> FINDMY_PUBLIC_KEY")
    print("  3. Server tu dong luu private key de doc vi tri")
