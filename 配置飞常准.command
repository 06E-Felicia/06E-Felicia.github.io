#!/bin/zsh
set -eu
cd -- "${0:A:h}"
python3 feimadata/private_key.py || { read -r '?配置未完成。按回车关闭…'; exit 1; }
read -r '?配置完成。请告诉助手“飞常准密钥已配置”。按回车关闭…'
