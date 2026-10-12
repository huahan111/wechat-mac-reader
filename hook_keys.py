"""
hook_keys.py — lldb 断点回调：在微信打开数据库的瞬间抓取 SQLCipher 密钥。

原理：macOS 微信 4.1.x 的数据库密钥不以明文驻留内存（扫内存是徒劳的），
只在调用系统 CommonCrypto 打开数据库的一瞬间出现在 CPU 寄存器里。
本脚本挂在 libcommonCrypto.dylib 的三个符号上（系统库符号不会被剥离）：

  CCCryptorCreate(op, alg, options, key, keyLength, iv)   → x3 = AES 密钥
  CCKeyDerivationPBKDF(alg, pwd, pwdLen, salt, saltLen, prf, rounds, dk, dkLen)
                                                          → x1 = 原始密钥, x3 = 盐
  CCHmacInit(ctx, alg, key, keyLength)                    → x2 = MAC 密钥

回调一律 return False（自动继续），不暂停进程，不触发反调试。

改写自 dylan121322/wxkey-hook（MIT License），针对 macOS 26 做了适配：
无需 sudo，配合 get-task-allow 重签名副本以同用户权限附加即可。
"""

import lldb

OUT = "/tmp/wxkey_captured.txt"

_seen = set()


def _read_mem(proc, ptr, length):
    """读取目标进程内存，返回 hex 字符串或 None。"""
    if ptr == 0 or length <= 0 or length > 256:
        return None
    err = lldb.SBError()
    data = proc.ReadMemory(ptr, length, err)
    return data.hex() if err.Success() else None


def _log(tag, fields):
    """去重日志：stdout + 追加写入 OUT 文件。"""
    line = f"[{tag}] " + " ".join(f"{k}={v}" for k, v in fields)
    if line in _seen:
        return
    _seen.add(line)
    try:
        with open(OUT, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def cryptor_bp(frame, bp_loc, internal_dict):
    """CCCryptorCreate — 抓 AES 密钥（微信用 32 字节）。"""
    proc = frame.GetThread().GetProcess()
    key_ptr = frame.FindRegister("x3").GetValueAsUnsigned()
    key_len = frame.FindRegister("x4").GetValueAsUnsigned()
    if key_ptr == 0 or key_len not in (16, 24, 32):
        return False
    key_hex = _read_mem(proc, key_ptr, int(key_len))
    if key_hex:
        _log("AESKEY", [("len", key_len), ("key", key_hex)])
    return False


def pbkdf_bp(frame, bp_loc, internal_dict):
    """CCKeyDerivationPBKDF — rounds=2 时 x1 即原始密钥，x3 为盐(盐^0x3A)。"""
    proc = frame.GetThread().GetProcess()
    pwd_ptr = frame.FindRegister("x1").GetValueAsUnsigned()
    pwd_len = frame.FindRegister("x2").GetValueAsUnsigned()
    salt_ptr = frame.FindRegister("x3").GetValueAsUnsigned()
    salt_len = frame.FindRegister("x4").GetValueAsUnsigned()
    rounds = frame.FindRegister("x6").GetValueAsUnsigned()
    if pwd_ptr == 0 or pwd_len == 0 or pwd_len > 64:
        return False
    pwd_hex = _read_mem(proc, pwd_ptr, int(pwd_len))
    salt_hex = _read_mem(proc, salt_ptr, int(salt_len)) if 0 < salt_len <= 32 else None
    if pwd_hex:
        _log("PBKDF", [("rounds", rounds), ("pwlen", pwd_len),
                        ("rawkey", pwd_hex), ("salt", salt_hex or "?")])
    return False


def hmac_bp(frame, bp_loc, internal_dict):
    """CCHmacInit — 抓 MAC 密钥（备用）。"""
    proc = frame.GetThread().GetProcess()
    key_ptr = frame.FindRegister("x2").GetValueAsUnsigned()
    key_len = frame.FindRegister("x3").GetValueAsUnsigned()
    if key_ptr == 0 or key_len == 0 or key_len > 64:
        return False
    key_hex = _read_mem(proc, key_ptr, int(key_len))
    if key_hex and key_len in (16, 24, 32):
        _log("MACKEY", [("len", key_len), ("key", key_hex)])
    return False
