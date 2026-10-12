#!/bin/bash
# extract_keys.sh — 自动抓取微信数据库密钥（无需 sudo，macOS 26 实测可用）
# 用法: bash extract_keys.sh
# 前提: 已运行 resign_wechat.sh 生成了 ~/WeChat-resign.app
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CAPTURED="/tmp/wxkey_captured.txt"
APP="$HOME/WeChat-resign.app"
WAIT_SECONDS=180

if [ ! -d "$APP" ]; then
    echo "[错误] 找不到 $APP，请先运行: bash resign_wechat.sh"; exit 1
fi

# 清理旧现场
killall WeChat 2>/dev/null
sleep 2
: > "$CAPTURED"; chmod 644 "$CAPTURED"

# lldb 命令：等微信启动就附加，布好三个断点后继续运行
cat > /tmp/wxkey_lldb.cmds <<'CMDS'
command script import HOOK_PATH
break set -n CCCryptorCreate
break command add -F hook_keys.cryptor_bp
break set -n CCKeyDerivationPBKDF
break command add -F hook_keys.pbkdf_bp
break set -n CCHmacInit
break command add -F hook_keys.hmac_bp
continue
CMDS
sed -i '' "s|HOOK_PATH|$SCRIPT_DIR/hook_keys.py|" /tmp/wxkey_lldb.cmds 2>/dev/null || \
    sed -i "s|HOOK_PATH|$SCRIPT_DIR/hook_keys.py|" /tmp/wxkey_lldb.cmds

echo "[*] 启动 lldb 等待附加..."
nohup lldb -b -o "process attach --name WeChat --waitfor" -s /tmp/wxkey_lldb.cmds \
    > /tmp/wxkey_lldb.log 2>&1 &
LLDB_PID=$!
sleep 4

echo "[*] 启动微信副本: $APP"
open "$APP"

echo "[*] 抓取中（最多 ${WAIT_SECONDS} 秒，微信登录后自动完成）..."
for i in $(seq 1 $((WAIT_SECONDS / 5))); do
    sleep 5
    N=$(grep -c AESKEY "$CAPTURED" 2>/dev/null || echo 0)
    kill -0 $LLDB_PID 2>/dev/null || break
    echo "    已捕捉密钥: $N"
done
kill $LLDB_PID 2>/dev/null

if [ ! -s "$CAPTURED" ]; then
    echo "[失败] 没抓到任何密钥，排查: /tmp/wxkey_lldb.log"; exit 1
fi

echo "[*] 匹配密钥与数据库并验证 ..."
python3 "$SCRIPT_DIR/match_keys.py" "$CAPTURED" "$SCRIPT_DIR/keys.json"

echo
echo "[完成] 密钥已保存到 $SCRIPT_DIR/keys.json（chmod 600，切勿外传）"
echo "下一步: python3 decrypt_db.py"
