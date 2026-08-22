#!/usr/bin/env bash
set -euo pipefail

# MatrixMedia 图形登录会话，仅供 SSH 隧道访问，禁止直接暴露公网端口。
session_dir="${HOME}/.cache/media-factory/matrixmedia-gui"
runtime_dir="${session_dir}/runtime"
display_number=99
display_address=":${display_number}"

mkdir -p "${session_dir}" "${runtime_dir}"
chmod 700 "${session_dir}" "${runtime_dir}"

stop_old_process() {
  local process_name="$1"
  local pid_file="${session_dir}/${process_name}.pid"
  local process_id

  [[ -f "${pid_file}" ]] || return 0
  process_id="$(tr -cd '0-9' < "${pid_file}")"
  if [[ -n "${process_id}" ]] && kill -0 "${process_id}" 2>/dev/null; then
    kill "${process_id}" 2>/dev/null || true
    for _ in {1..20}; do
      kill -0 "${process_id}" 2>/dev/null || break
      sleep 0.1
    done
  fi
  rm -f "${pid_file}"
}

start_background_process() {
  local process_name="$1"
  shift
  nohup "$@" >"${session_dir}/${process_name}.log" 2>&1 </dev/null &
  echo "$!" >"${session_dir}/${process_name}.pid"
}

for process_name in matrixmedia websockify x11vnc openbox xvfb; do
  stop_old_process "${process_name}"
done

# 只清理由本脚本使用且已确认没有存活 Xvfb 的 99 号显示锁。
if [[ -f "/tmp/.X${display_number}-lock" ]]; then
  lock_process_id="$(tr -cd '0-9' < "/tmp/.X${display_number}-lock")"
  if [[ -z "${lock_process_id}" ]] || ! kill -0 "${lock_process_id}" 2>/dev/null; then
    rm -f "/tmp/.X${display_number}-lock" "/tmp/.X11-unix/X${display_number}"
  fi
fi

export DISPLAY="${display_address}"
export XDG_RUNTIME_DIR="${runtime_dir}"
export MATRIXMEDIA_DISABLE_TELEMETRY=1
unset ELECTRON_RUN_AS_NODE DBUS_SESSION_BUS_ADDRESS

start_background_process xvfb Xvfb "${display_address}" -screen 0 1440x900x24 -nolisten tcp
for _ in {1..50}; do
  [[ -S "/tmp/.X11-unix/X${display_number}" ]] && break
  sleep 0.1
done
[[ -S "/tmp/.X11-unix/X${display_number}" ]] || {
  echo "Xvfb 启动失败，请检查 ${session_dir}/xvfb.log" >&2
  exit 1
}

start_background_process openbox openbox-session
start_background_process x11vnc x11vnc -display "${display_address}" -rfbport 5900 -localhost -forever -shared -nopw -noxdamage
start_background_process websockify websockify --web=/usr/share/novnc 127.0.0.1:6080 127.0.0.1:5900
start_background_process matrixmedia /usr/local/bin/matrixmedia --no-sandbox --disable-gpu --disable-software-rasterizer --disable-dev-shm-usage

sleep 2
for process_name in xvfb openbox x11vnc websockify matrixmedia; do
  process_id="$(cat "${session_dir}/${process_name}.pid")"
  if ! kill -0 "${process_id}" 2>/dev/null; then
    echo "${process_name} 启动失败，请检查 ${session_dir}/${process_name}.log" >&2
    exit 1
  fi
done

echo "MatrixMedia 图形会话已启动。"
echo "请通过 SSH 隧道访问：http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale"
