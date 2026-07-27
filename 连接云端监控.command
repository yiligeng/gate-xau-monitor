#!/bin/zsh

set -e

key_path="${LIGHTSAIL_SSH_KEY_PATH:-}"
remote_host="${LIGHTSAIL_REMOTE_HOST:-}"
local_port="18765"

if [[ -z "$key_path" || -z "$remote_host" ]]; then
  echo "请先在本机设置 LIGHTSAIL_SSH_KEY_PATH 和 LIGHTSAIL_REMOTE_HOST。"
  echo "示例："
  echo "export LIGHTSAIL_SSH_KEY_PATH=\"/path/to/key.pem\""
  echo "export LIGHTSAIL_REMOTE_HOST=\"your.server.example\""
  read -k 1 "?按任意键退出..."
  exit 1
fi

if [[ ! -f "$key_path" ]]; then
  echo "找不到 Lightsail SSH 密钥。请检查 LIGHTSAIL_SSH_KEY_PATH。"
  read -k 1 "?按任意键退出..."
  exit 1
fi

echo "正在建立到 AWS Lightsail 的加密连接..."
ssh \
  -i "$key_path" \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -N \
  -L "127.0.0.1:${local_port}:127.0.0.1:8765" \
  "ubuntu@${remote_host}" &

tunnel_pid=$!
trap 'kill "$tunnel_pid" 2>/dev/null || true' EXIT INT TERM

for attempt in {1..20}; do
  if curl --fail --silent "http://127.0.0.1:${local_port}/api/snapshot" >/dev/null; then
    open "http://127.0.0.1:${local_port}/"
    echo "云端监控已打开。关闭此窗口即可断开连接。"
    wait "$tunnel_pid"
    exit $?
  fi
  sleep 0.5
done

echo "连接已建立，但监控页面未能及时响应。"
exit 1
