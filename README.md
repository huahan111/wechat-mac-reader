# wechat-mac-reader — macOS 微信聊天记录读取工具

读取 **本机、本人** 微信 (macOS 4.1.x) 的本地聊天数据库并导出为可读文本。
纯本地运行，无任何网络请求。实测环境：macOS 26 + 微信 4.1.15（Apple Silicon）。

## 原理（一句话版）

微信 4.1 起数据库密钥不再明文存于内存（扫内存没用），只在打开数据库的一瞬间
出现在 CPU 寄存器里。本工具把微信复制一份重签名（允许调试），用 lldb 在系统
加密库 CommonCrypto 的函数上布断点，启动瞬间抓下密钥，再逐页解密数据库。

> 致谢：思路来自 [dylan121322/wxkey-hook](https://github.com/dylan121322/wxkey-hook)（MIT）
> 与看雪论坛社区的逆向研究；本项目在其基础上适配 macOS 26（免 sudo），
> 并补充了批量解密与聊天记录导出。

## 使用步骤（共 4 条命令）

```bash
# 0. 依赖：Xcode 命令行工具 + Python 3.10+
xcode-select --install          # 已装过可跳过
pip3 install zstandard          # 导出聊天记录需要

# 1. 复制并重签名微信（只做一次；登录状态通用）
bash resign_wechat.sh

# 2. 抓取数据库密钥（会自动重启微信，登录后自动完成，约 1-3 分钟）
bash extract_keys.sh

# 3. 解密数据库到 decrypted/（首次全量约几分钟）
python3 decrypt_db.py

# 4. 导出聊天记录
python3 export_chats.py --list                  # 看有哪些会话
python3 export_chats.py --chat 某群名 --since 2026-09-01
```

导出结果在 `exports/` 目录，每行格式：`[2026-10-11 15:30] 昵称: 内容`。

## 常见问题

- **抓不到密钥**：确认用的是 `~/WeChat-resign.app`（重签名副本）而不是原版微信；
  微信升级后需重新运行 resign + extract。
- **某几个库提示无匹配**：新出现的数据库要重新抓一次密钥（重跑 extract_keys.sh）。
- **微信自动更新把重签名覆盖了**：重新跑一遍 resign + extract 即可。

## ⚠️ 法律与道德边界（必读）

- 仅限用于 **自己的设备、自己的微信账号** 的数据备份与研究。
- `keys.json` 是你全部聊天记录的解密钥匙，**绝不分享、绝不提交到 git**（已 gitignore）。
- `decrypted/`、`exports/` 是明文聊天记录，同样不要外传。
- 请遵守当地法律与微信用户协议；滥用造成的后果自负。

## License

MIT
