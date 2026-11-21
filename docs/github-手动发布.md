# 自行推送到 GitHub

目标仓库：https://github.com/itbulu/LeBench

```bash
cd /path/to/LeBench

git init -b main      # 若尚未初始化
git add .
git status
git commit -m "Update docs and installer for itbulu/LeBench"

git remote add origin https://github.com/itbulu/LeBench.git
# 若 remote 已存在：
# git remote set-url origin https://github.com/itbulu/LeBench.git

git push -u origin main
```

可选 tag：

```bash
git tag v0.2.0
git push origin v0.2.0
```
