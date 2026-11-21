# 自行推送到 GitHub（本仓库不代为提交）

开发侧已准备好安装脚本与 CI，请你在本机自行完成：

```bash
cd /path/to/LeBench   # Windows: e:\脚本开发\LeBench

git init -b main      # 若尚未初始化
git add .
git status            # 确认未包含 .venv / reports / __pycache__
git commit -m "Initial LeBench 0.2.0 with one-click installer"

# 在 GitHub 网页创建空仓库 LeBench 后：
git remote add origin https://github.com/YOUR_GITHUB_USER/LeBench.git
git push -u origin main
```

推送后建议：

1. 把 `install.sh` / `scripts/bootstrap.sh` 里的默认 `YOUR_GITHUB_USER` 改成真实用户名，再提交一次；或安装时始终传 `--repo`。
2. 在 Linux VPS 用 `bash install.sh --local --yes`（先 scp/clone）或远程一键安装验证。

可选打 tag：

```bash
git tag v0.2.0
git push origin v0.2.0
```
