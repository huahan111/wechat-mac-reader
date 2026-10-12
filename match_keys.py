#!/usr/bin/env python3
"""
match_keys.py — 把抓到的候选密钥与本地数据库逐一 HMAC 验证配对。
用法: python3 match_keys.py /tmp/wxkey_captured.txt keys.json [db_dir]
"""

import hashlib
import hmac
import json
import os
import re
import struct
import sys

PAGE = 4096


def find_db_dir():
    base = os.path.expanduser(
        "~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files")
    if not os.path.isdir(base):
        return None
    best, best_mtime = None, -1
    for wxid in os.listdir(base):
        d = os.path.join(base, wxid, "db_storage")
        if os.path.isdir(d):
            m = os.path.getmtime(d)
            if m > best_mtime:
                best, best_mtime = d, m
    return best


def verify(enc_key, page1):
    salt = page1[:16]
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, dklen=32)
    h = hmac.new(mac_key, page1[16:4032], hashlib.sha512)
    h.update(struct.pack("<I", 1))
    return h.digest() == page1[4032:4096]


def main():
    captured_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/wxkey_captured.txt"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "keys.json"
    db_dir = sys.argv[3] if len(sys.argv) > 3 else find_db_dir()
    if not db_dir or not os.path.isdir(db_dir):
        print("[错误] 找不到 db_storage 目录"); sys.exit(1)
    print(f"数据库目录: {db_dir}")

    keys = set()
    for line in open(captured_file, encoding="utf-8", errors="replace"):
        for h in re.findall(r"\b([0-9a-f]{32,64})\b", line):
            if len(h) % 2 == 0:
                keys.add(bytes.fromhex(h))
    keys32 = {k for k in keys if len(k) == 32}
    print(f"候选 32 字节密钥 {len(keys32)} 个")

    result = {}
    dbs = []
    for root, _dirs, files in os.walk(db_dir):
        for n in files:
            if n.endswith(".db"):
                p = os.path.join(root, n)
                rel = os.path.relpath(p, db_dir)
                with open(p, "rb") as f:
                    page1 = f.read(PAGE)
                if len(page1) < PAGE:
                    continue
                dbs.append((rel, page1))

    for rel, page1 in dbs:
        for k in keys32:
            if verify(k, page1):
                result[rel] = k.hex()
                print(f"[OK] {rel}")
                break
        else:
            print(f"[--] {rel} 无匹配（可能是新库，重新抓一次）")

    with open(out_file, "w") as f:
        json.dump(result, f, indent=2)
    os.chmod(out_file, 0o600)
    print(f"命中 {len(result)}/{len(dbs)} -> {out_file}")


if __name__ == "__main__":
    main()
