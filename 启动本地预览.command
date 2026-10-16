#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  print '未找到 Python 3。请安装 Python 3 后重新打开；网页运行不需要安装 NumPy。'
  read -r '?按回车关闭…'
  exit 1
fi
python3 -m simulation.preview
if (( $? != 0 )); then
  read -r '?预览启动失败，请保留上方错误信息。按回车关闭…'
fi
