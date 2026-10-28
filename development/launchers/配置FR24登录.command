#!/bin/zsh
set -eu
cd -- "${0:A:h}/../.."
task_python=''
for candidate in .venv-fr24/bin/python .venv/bin/python python3; do
  if "$candidate" -c 'import playwright' >/dev/null 2>&1; then
    task_python="$candidate"
    break
  fi
done
if [[ -z "$task_python" ]]; then
  print '首次使用：为 FR24 建立独立 Python 环境并安装项目依赖。'
  python3 -m venv .venv-fr24
  .venv-fr24/bin/python -m pip install -r flightdata/requirements.txt
  task_python='.venv-fr24/bin/python'
fi
"$task_python" flightdata/export_session.py || { read -r '?未完成登录，请保留上方提示。按回车关闭…'; exit 1; }
read -r '?导出已完成。不要上传登录文件到仓库。按回车关闭…'
