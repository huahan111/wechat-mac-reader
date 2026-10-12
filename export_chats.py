#!/usr/bin/env python3
"""
export_chats.py — 从解密后的数据库导出聊天记录为可读文本。
用法:
  python3 export_chats.py --list                  # 列出所有会话及消息数
  python3 export_chats.py --chat 某某群             # 导出名称含"某某群"的会话
  python3 export_chats.py --chat 某某群 --since 2026-09-01
依赖: pip install zstandard   （解压 4.x 的压缩消息，必需）
输出: exports/<会话名>.txt，每行 [月-日 时:分] 发送者: 内容
"""

import argparse
import datetime
import glob
import os
import re
import sqlite3
import sys

try:
    import zstandard
except ImportError:
    print("[错误] 缺少依赖: pip install zstandard"); sys.exit(1)

TYPE_NAME = {3: "[图片]", 34: "[语音]", 43: "[视频]", 47: "[表情]",
             51: "[状态]", 42: "[名片]", 10000: "[系统消息]"}


def dec_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "decrypted")


def clean(c):
    if isinstance(c, bytes):
        try:
            c = zstandard.ZstdDecompressor().decompress(c).decode("utf-8", "replace")
        except Exception:
            return "[无法解压]"
    if not c:
        return ""
    if c.endswith(":\n"):
        return "[图片/表情]"
    m = re.match(r"^(.+?):\n(.*)$", c, re.S)
    body = m.group(2) if m else c
    if "<title>" in body:
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", body, re.S)
        if t:
            return f"[卡片] {t.group(1).strip()[:100]}"
    if body.startswith("<?xml") or body.startswith("<msg"):
        return "[XML消息]"
    return body.strip()


def load_all():
    """返回 (chats, nick, msg_dbs)
    chats: {table_name: {"db": path, "user": user_name, "count": n}}
    nick:  {user_name: 昵称}
    """
    d = dec_dir()
    msg_dbs = sorted(glob.glob(os.path.join(d, "message_message_*.db")))
    chats = {}
    nick = {}
    contact = os.path.join(d, "contact_contact.db")
    if os.path.exists(contact):
        c = sqlite3.connect(contact)
        for u, n in c.execute("SELECT username, nick_name FROM contact"):
            if u and n:
                nick[u] = n
        c.close()
    for db in msg_dbs:
        conn = sqlite3.connect(db)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")]
        for t in tables:
            try:
                r = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                cnt = r[0]
            except sqlite3.Error:
                continue
            user = None
            md5 = t[4:]
            # Name2Id 里 user_name 的 md5 即表名后缀
            for un, in conn.execute("SELECT user_name FROM Name2Id"):
                import hashlib
                if hashlib.md5(un.encode()).hexdigest() == md5:
                    user = un
                    break
            chats[t] = {"db": db, "user": user, "count": cnt}
        conn.close()
    return chats, nick, msg_dbs


def chat_label(chats, nick):
    """table -> 显示名"""
    labels = {}
    for t, info in chats.items():
        u = info["user"] or t
        labels[t] = nick.get(u, u)
    return labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出所有会话")
    ap.add_argument("--chat", help="按名称筛选会话（模糊匹配）")
    ap.add_argument("--since", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="输出目录（默认: 脚本所在目录/exports）")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = args.out or os.path.join(here, "exports")

    chats, nick, _ = load_all()
    labels = chat_label(chats, nick)

    if args.list:
        for t, info in sorted(chats.items(), key=lambda x: -x[1]["count"]):
            print(f"{info['count']:>8}  {labels[t]}")
        return

    if not args.chat:
        print("用法: --list 查看会话 / --chat 名称 导出"); return

    start_ts = 0
    if args.since:
        start_ts = int(datetime.datetime.strptime(args.since, "%Y-%m-%d").timestamp())

    targets = [t for t, l in labels.items() if args.chat in l]
    if not targets:
        print(f"[错误] 没找到名称含「{args.chat}」的会话，用 --list 查看"); return

    os.makedirs(out_dir, exist_ok=True)
    for t in targets:
        info = chats[t]
        label = re.sub(r'[\\/:*?"<>|]', "_", labels[t])
        conn = sqlite3.connect(info["db"])
        name2id = dict(conn.execute("SELECT rowid, user_name FROM Name2Id").fetchall())
        out_path = os.path.join(out_dir, f"{label}.txt")
        n = 0
        with open(out_path, "w", encoding="utf-8") as out:
            for lt, sid, ts, c in conn.execute(
                    f"SELECT local_type, real_sender_id, create_time, message_content "
                    f"FROM {t} WHERE create_time >= ? ORDER BY sort_seq", (start_ts,)):
                when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                who = nick.get(name2id.get(sid, ""), name2id.get(sid, str(sid)))
                if lt == 1:
                    txt = clean(c) or "[空]"
                elif lt in TYPE_NAME:
                    txt = TYPE_NAME[lt]
                elif lt == 49:
                    txt = clean(c) or "[卡片]"
                else:
                    txt = f"[类型{lt}]"
                out.write(f"[{when}] {who}: {txt}\n")
                n += 1
        conn.close()
        print(f"[OK] {label} -> {out_path} ({n} 条)")


if __name__ == "__main__":
    main()
