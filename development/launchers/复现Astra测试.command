#!/bin/zsh
cd -- "${0:A:h}/../.." || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  print '未找到 Python 3。启动器只需要 Python 3，不需要安装 NumPy 或重新计算。'
  read -r '?按回车关闭…'
  exit 1
fi
python3 -m simulation.test_replay
if (( $? != 0 )); then
  read -r '?测试回放启动失败，请保留上方错误信息。按回车关闭…'
fi
