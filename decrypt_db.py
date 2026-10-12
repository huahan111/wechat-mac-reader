#!/usr/bin/env python3
"""
decrypt_db.py — 用密钥把 SQLCipher 加密的微信数据库解密成明文 SQLite。
用法:
  python3 decrypt_db.py                 # 解密 keys.json 里的全部数据库到 ./decrypted/
  python3 decrypt_db.py -i message/message_0.db   # 只解密指定库

参数（macOS 微信 4.1.x 实测）: page=4096, reserve=80(IV16+HMAC64),
AES-256-CBC, raw-key 模式（密钥即 AES key，无 PBKDF2 拉伸）。
"""

import ctypes
import hashlib
import hmac
import json
import os
import struct
import sys

_cc = ctypes.CDLL("/usr/lib/system/libcommonCrypto.dylib")
CCCrypt = _cc.CCCrypt
CCCrypt.restype = ctypes.c_int
CCCrypt.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

PAGE, SALT, IV, HMAC_SZ, RESERVE = 4096, 16, 16, 64, 80
SQLITE_HDR = b"SQLite format 3\x00"


def aes_cbc_decrypt(key, iv, ct):
    buf = ctypes.create_string_buffer(len(ct) + 16)
    moved = ctypes.c_size_t(0)
    st = CCCrypt(1, 0, 0, key, len(key), iv, ct, len(ct), buf, len(buf), ctypes.byref(moved))
    if st != 0:
        raise RuntimeError(f"CCCrypt status {st}")
    return buf.raw[:moved.value]


def verify_page1(path, key):
    with open(path, "rb") as f:
        page = f.read(PAGE)
    if len(page) < PAGE:
        return False
    salt = page[:SALT]
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", key, mac_salt, 2, dklen=32)
    hh = hmac.new(mac_key, page[SALT:PAGE - RESERVE + IV], hashlib.sha512)
    hh.update(struct.pack("<I", 1))
    return hh.digest() == page[PAGE - HMAC_SZ:PAGE]


def decrypt_db(src, dst, key, quiet=False):
    size = os.path.getsize(src)
    pages = size // PAGE + (1 if size % PAGE else 0)
    if not verify_page1(src, key):
        print(f"  [跳过] {src} 密钥校验失败")
        return False
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        pgno = 1
        while True:
            page = fin.read(PAGE)
            if not page:
                break
            if len(page) < PAGE:
                page += b"\x00" * (PAGE - len(page))
            iv = page[PAGE - RESERVE:PAGE - RESERVE + IV]
            if pgno == 1:
                fout.write(SQLITE_HDR + aes_cbc_decrypt(key, iv, page[SALT:PAGE - RESERVE]) + b"\x00" * RESERVE)
            else:
                fout.write(aes_cbc_decrypt(key, iv, page[:PAGE - RESERVE]) + b"\x00" * RESERVE)
            pgno += 1
    if not quiet:
        print(f"  [OK] {os.path.basename(src)} -> {dst} ({pages} 页)")
    return True


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    keys_file = os.path.join(here, "keys.json")
    if not os.path.exists(keys_file):
        print("[错误] 找不到 keys.json，先运行 extract_keys.sh"); sys.exit(1)
    raw = json.load(open(keys_file))
    # 兼容两种格式: {rel: hex} 或 {rel: {"enc_key": hex}}
    keys = {k: (v["enc_key"] if isinstance(v, dict) else v) for k, v in raw.items()}

    db_dir = None
    base = os.path.expanduser(
        "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files")
    best, best_m = None, -1
    for wxid in os.listdir(base):
        d = os.path.join(base, wxid, "db_storage")
        if os.path.isdir(d) and os.path.getmtime(d) > best_m:
            db_dir, best_m = d, os.path.getmtime(d)
    if not db_dir:
        print("[错误] 找不到微信 db_storage"); sys.exit(1)
    print(f"数据库目录: {db_dir}")

    only = None
    if "-i" in sys.argv:
        only = sys.argv[sys.argv.index("-i") + 1]
    out_dir = os.path.join(here, "decrypted")
    os.makedirs(out_dir, exist_ok=True)

    ok = 0
    for rel, hexkey in sorted(keys.items()):
        if only and rel != only:
            continue
        src = os.path.join(db_dir, rel)
        dst = os.path.join(out_dir, rel.replace("/", "_"))
        if not os.path.exists(src):
            continue
        mb = os.path.getsize(src) / 1048576
        print(f"解密 {rel} ({mb:.1f}MB) ...")
        if decrypt_db(src, dst, bytes.fromhex(hexkey), quiet=False):
            ok += 1
    print(f"\n完成 {ok} 个库 -> {out_dir}")


if __name__ == "__main__":
    main()
