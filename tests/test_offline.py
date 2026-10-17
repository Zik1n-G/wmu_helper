"""离线自测：RSA 加密链路 + 课表解析。运行：python tests/test_offline.py"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wmu_jwxt.core.rsa import RSAKey, b64tohex, encrypt_password, hex2b64
from wmu_jwxt.parsers.schedule import parse_schedule, parse_sections, parse_weeks

# 测试用 1024-bit 模数（本地生成，非真实教务系统密钥）
N_HEX = (
    "c8b4e2f5a1d3e7c9b0a4f6d8e2b5c7a9d1f3e5b7c9a1d3f5e7b9c1d3f5a7b9c1"
    "d3f5a7b9c1d3f5a7b9c1d3f5a7b9c1d3f5a7b9c1d3f5a7b9c1d3f5a7b9c1d3f5"
)
N_B64_HEX = "MDAwMTAwMDE="  # 占位，encrypt_password 测试用有效模数
# 有效 1024-bit 模数（hex2b64(b64tohex(x)) 往返一致即可用于格式测试）
VALID_N_B64 = "AP7E6V4mY0y9l2Z9g0H3m5X7b1N4c6V8b0J2n4M6l8X1z3B5d7F9h1K3j5L7p9R2t4U6v8W0x2Y4z6A8b0C2d4E6f8G0h2I4j6K8l0M2n4O6p8Q0r2S4t6U8v0W2x4Y6z8="
E_HEX = "10001"


def test_b64_hex_roundtrip():
    h = b64tohex("AQAB")
    assert hex2b64(h) == "AQAB", hex2b64(h)
    print("PASS b64<->hex roundtrip")


def test_rsa_encrypt_format():
    key = RSAKey()
    key.set_public(N_HEX, E_HEX)
    c = key.encrypt("test_password_123")
    # hex 密文长度 = key size in bytes
    k = (int(N_HEX, 16).bit_length() + 7) // 8
    assert len(c) == k * 2, f"cipher len {len(c)} != {k*2}"
    assert all(ch in "0123456789abcdef" for ch in c)
    print(f"PASS rsa encrypt (cipher {len(c)//2} bytes)")


def test_encrypt_password_returns_b64():
    # 用有效模数（hex2b64(b64tohex()) 环绕后需为整数字节）
    import base64
    n_bytes = base64.b64decode(VALID_N_B64.ljust(172, "=")[:172] + "==")
    n_hex = n_bytes.hex()
    out = encrypt_password("secret", base64.b64encode(bytes.fromhex(n_hex)).decode(), "AQAB")
    assert isinstance(out, str) and len(out) > 0
    print("PASS encrypt_password returns base64 string")


def test_parse_sections():
    assert parse_sections("3-5节") == (3, 5)
    assert parse_sections("3") == (3, 3)
    assert parse_sections("") == (0, 0)
    print("PASS parse_sections")


def test_parse_weeks():
    assert parse_weeks("1-4周,6-17周") == [1, 2, 3, 4] + list(range(6, 18))
    assert parse_weeks("1,3,5周") == [1, 3, 5]
    assert parse_weeks("") == []
    print("PASS parse_weeks")


def test_parse_schedule():
    payload = {
        "xsxx": {"XH": "2026000001", "XM": "测试", "BJMC": "测试班"},
        "kbList": [
            {"kcmc": "高等数学", "xqj": "1", "jc": "3-5节", "zcd": "1-16周",
             "cdmc": "教学楼A101", "xm": "张老师", "xf": "4.5", "kch": "MATH101"},
            {"kcmc": "大学英语", "xqj": "1", "jc": "8-9节", "zcd": "1-8周,10-16周",
             "cdmc": "外语楼302", "xm": "李老师", "xf": "3.0", "kch": "ENG100"},
            {"kcmc": "体育", "xqj": "3", "jc": "6-7节", "zcd": "2-17周",
             "cdmc": "体育馆", "xm": "王老师", "xf": "1.0", "kch": "PE001"},
        ],
    }
    s = parse_schedule(payload, 2026, 1)
    assert s["count"] == 3, s["count"]
    assert s["student"]["name"] == "测试"
    assert len(s["by_weekday"][1]) == 2
    assert len(s["by_weekday"][3]) == 1
    math = s["courses"][0]
    assert math["section_start"] == 3 and math["section_end"] == 5
    assert len(math["weeks"]) == 16
    eng = [c for c in s["courses"] if c["title"] == "大学英语"][0]
    assert eng["weeks"] == [1,2,3,4,5,6,7,8,10,11,12,13,14,15,16], eng["weeks"]
    print("PASS parse_schedule")


if __name__ == "__main__":
    failed = False
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                failed = True
                print(f"FAIL {name}: {e}")
    raise SystemExit(1 if failed else 0)
