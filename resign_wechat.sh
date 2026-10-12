#!/bin/bash
# resign_wechat.sh — 把微信复制一份并重签名，允许调试器附加（抓密钥必需，只做一次）
# 用法: bash resign_wechat.sh
set -euo pipefail

SRC="/Applications/WeChat.app"
DST="$HOME/WeChat-resign.app"

if [ ! -d "$SRC" ]; then
    echo "[错误] 找不到 $SRC，请先安装微信"; exit 1
fi

echo "[*] 复制微信到 ~/WeChat-resign.app ..."
rm -rf "$DST"
cp -R "$SRC" "$DST"

echo "[*] 重签名（仅外层，附加 get-task-allow 权限）..."
codesign --force --sign - --entitlements "$(dirname "$0")/debug.entitlements" "$DST"

echo
echo "[完成] 重签名副本: $DST"
echo "之后抓密钥、日常使用都可以用它（登录状态通用）。"
