#!/usr/bin/env bash
# 將目前的程式碼 + 最新資料庫發布到 streamlit 分支，供 Streamlit Community Cloud 部署。
# 以單一 commit 強制覆寫，資料庫不會在 git 歷史中累積。
set -euo pipefail

DB=data/usequity.db
if [ ! -f "$DB" ]; then
  echo "::warning::找不到 $DB，略過發布（先執行一次 FMP 選股回測 workflow）"
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
# orphan 分支沿用目前 HEAD 的檔案樹，只額外加入資料庫（.gitignore 排除了 *.db，需 -f）
git checkout -q --orphan streamlit-publish
git add -f "$DB"
git commit -q -m "streamlit snapshot $(TZ=Asia/Taipei date '+%F %H:%M') (source ${GITHUB_SHA:-local})"
git push -q -f origin HEAD:streamlit
echo "已發布到 streamlit 分支（資料庫 $(du -h "$DB" | cut -f1)）"
