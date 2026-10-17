import base64


def b64tohex(s: str) -> str:
    """base64 -> hex，与教务系统前端 login.js 的 b64tohex 行为一致。"""
    b = base64.b64decode(s)
    return b.hex()


def hex2b64(h: str) -> str:
    """hex -> base64，对应前端 hex2b64。"""
    raw = bytes.fromhex(h)
    return base64.b64encode(raw).decode()


class RSAKey:
    """极简 RSA 公钥加密实现（纯 Python，无第三方依赖）。

    只实现教务系统登录需要的公钥加密：PKCS#1 v1.5 padding + modexp。
    """

    @staticmethod
    def _egcd(a: int, b: int):
        if a == 0:
            return (b, 0, 1)
        g, y, x = RSAKey._egcd(b % a, a)
        return (g, x - (b // a) * y, y)

    @staticmethod
    def _gcd(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a

    @staticmethod
    def _modinv(a: int, m: int) -> int:
        g, x, _ = RSAKey._egcd(a, m)
        if g != 1:
            raise ValueError("modular inverse does not exist")
        return x % m

    def __init__(self):
        self.n = 0
        self.e = 0

    def set_public(self, modulus_hex: str, exponent_hex: str) -> None:
        self.n = int(modulus_hex, 16)
        self.e = int(exponent_hex, 16)

    def encrypt(self, message: str) -> str:
        """PKCS#1 v1.5 type 2 padding，返回 hex 密文（与前端 hex2b64(rsaKey.encrypt(mm)) 对接）。"""
        msg = message.encode("utf-8")
        k = (self.n.bit_length() + 7) // 8
        if k < len(msg) + 11:
            raise ValueError("message too long for RSA key size")
        # PKCS#1 v1.5: 0x00 0x02 <非零随机填充> 0x00 <明文>
        padding_len = k - len(msg) - 3
        padding = bytearray()
        while len(padding) < padding_len:
            byte = _random_byte()
            if byte != 0:
                padding.append(byte)
        block = b"\x00\x02" + bytes(padding) + b"\x00" + msg
        m = int.from_bytes(block, "big")
        c = pow(m, self.e, self.n)
        return c.to_bytes(k, "big").hex()


def _random_byte() -> int:
    import os

    return int.from_bytes(os.urandom(1), "big")


def encrypt_password(password: str, modulus_b64: str, exponent_b64: str) -> str:
    """登录页 login.js 的完整链路复刻：
    setPublic(b64tohex(modulus), b64tohex(exponent)) -> hex2b64(rsaKey.encrypt(password))。
    """
    key = RSAKey()
    key.set_public(b64tohex(modulus_b64), b64tohex(exponent_b64))
    return hex2b64(key.encrypt(password))
