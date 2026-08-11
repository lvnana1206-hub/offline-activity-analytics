#!/bin/bash
# 代理商周报双模板自动推送脚本
# crontab: 每周五 18:00 执行
# 5 18 * * 5 /path/to/project/scripts/weekly_push_cron.sh

cd /path/to/project
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
PYTHON=/opt/anaconda3/bin/python3

LOG=/tmp/weekly_push_cron.log
echo "=== $(date '+%Y-%m-%d %H:%M:%S') 双模板周报推送开始 ===" >> $LOG

# 代理商版推送（晾晒群）
DEALER_RESULT=$(curl -s -X POST "http://127.0.0.1:8080/api/weekly_report/push_template?template=dealer" 2>/dev/null)
echo "[代理商版] $DEALER_RESULT" >> $LOG
DEALER_OK=$(echo "$DEALER_RESULT" | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('push_ok',False))" 2>/dev/null)

# 内部版推送（管理群）
INTERNAL_RESULT=$(curl -s -X POST "http://127.0.0.1:8080/api/weekly_report/push_template?template=internal" 2>/dev/null)
echo "[内部版] $INTERNAL_RESULT" >> $LOG
INTERNAL_OK=$(echo "$INTERNAL_RESULT" | $PYTHON -c "import sys,json; print(json.load(sys.stdin).get('push_ok',False))" 2>/dev/null)

if [ "$DEALER_OK" = "True" ] && [ "$INTERNAL_OK" = "True" ]; then
  echo "双模板推送成功" >> $LOG
else
  echo "推送异常，请检查日志" >> $LOG
fi
echo "=== 推送结束 ===" >> $LOG
