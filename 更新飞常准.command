#!/bin/zsh
set -eu
cd -- "${0:A:h}"
print '将读取七机场双向大屏（最多14次），并按航线批量补充机号/机型（最多40次详情查询），会使用飞常准额度。'
print '已有有效缓存会复用；照片按注册号向 PlaneSpotters 查询，最多60次。首次不保证所有航班资料齐全。'
read -r '?按回车开始，或按 Control+C 取消…'
python3 -B -m feimadata.collect || { read -r '?未全部完成，请保留提示。按回车关闭…'; exit 1; }
read -r '?快照已保存。刷新 Feimadat.html 即可查看。按回车关闭…'
