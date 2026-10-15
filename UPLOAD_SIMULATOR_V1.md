# 手动上传本项目

当前本地分支为 `main`，origin 已配置为 `ssh://git@ssh.github.com:443/06E-Felicia/06E-Felicia.github.io.git`，并使用现有密钥 `id_ed25519_felicia`。以下命令逐条执行；没有使用强制推送，不覆盖远端历史。模拟器无需 API key。

## 1. 进入项目并检查文件

```sh
cd /Users/ethan/Desktop/06E-Felicia.github.io-main
git status --short
```

应看到 `M`（已修改）和 `??`（新增）文件，包括模拟器、首页、脚本、样式、测试、运行时和截图。先确认没有不想上传的私人文件；`.env` 和本地虚拟环境已忽略。

## 2. 解锁现有 SSH 密钥

```sh
ssh-add --apple-use-keychain /Users/ethan/.ssh/id_ed25519_felicia
```

若提示 `Enter passphrase for ...`，输入当初设定的**密钥口令**，不是 GitHub 账户密码。输入时终端不显示字符或星号，属于正常现象，输完按回车。成功应提示 `Identity added`；不要把口令或私钥粘贴到聊天里。

## 3. 检查 GitHub 连接

```sh
ssh -i /Users/ethan/.ssh/id_ed25519_felicia -o IdentitiesOnly=yes -o ConnectTimeout=15 -T -p 443 git@ssh.github.com
```

成功应包含 `Hi 06E-Felicia! You've successfully authenticated`。同时出现“不提供 shell access”是正常的，SSH 测试退出码 1 也不表示认证失败。[GitHub 官方 SSH 443 说明](https://docs.github.com/en/authentication/troubleshooting-ssh/using-ssh-over-the-https-port)、[SSH 测试说明](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection)。首次出现主机真实性提示时，先核对官方公布的指纹再确认；连接超时或 `Permission denied` 时停止，不继续推送。

## 4. 保存本地全部项目变更

```sh
git add .
git commit -m "Release simulator V1 and Thursday update announcement"
```

`git add` 通常没有输出。提交应显示 `[main ...]` 和变更文件数。若显示 `nothing to commit`，说明当前内容已保存，可以继续同步。

## 5. 同步远端的天气自动更新

```sh
git pull --rebase origin main
```

这是把本地提交重放在远端最新提交之上，不生成 merge 提交，也不强行覆盖远端天气更新。成功一般显示 `Successfully rebased...` 或 `Already up to date`。若出现 `CONFLICT`，停止并把错误发给我；想恢复到同步前状态可执行 `git rebase --abort`，不要强制推送。

## 6. 推送

```sh
git push origin main
```

应出现对象上传进度及 `main -> main`。若天气工作流恰好又提交了数据导致 `non-fast-forward`，重复第 5、6 步；不要使用 `--force`。推送成功后可用 `git status -sb` 检查应无待提交文件。

## 7. 发布 GitHub Pages

打开仓库的 Actions → **自动更新天气数据** → **Run workflow**，选择 `main`，开关保留「保持当前设置」。此工作流会上传并发布整个网站，完成后刷新主页检查更新提示板和模拟器。

若工作流提示 Pages 配置问题，检查 Settings → Pages → Source 为 **GitHub Actions**。不需要先跑昂贵的「运行强对流模拟」批量任务；访客模拟是在本机浏览器计算，网站发布与批量实验互相独立。
