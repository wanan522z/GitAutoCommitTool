# Git Auto Commit Tool

`Git Auto Commit Tool` 是一个给 Windows 用户使用的桌面小工具，用来帮你对本地 Git 项目做周期性自动提交，并在需要时手动整理提交、查看历史和推送到 GitHub。

## 适合什么场景

- 你想给正在开发的项目定时留存快照，减少忘记提交的情况
- 你想把仓库状态、提交记录、待推送数量放在一个窗口里查看
- 你希望手动提交时也能按常见 Commit 规范快速写标题和内容
- 你希望在不打开命令行的情况下，快速完成本地提交和推送

## 当前功能

- 选择本地 Git 项目文件夹
- 配置或更新 `origin` 远程地址
- 保存当前仓库的 Git 用户名和邮箱
- 按设定间隔执行 `git add -A` + 自动 `commit`
- 手动执行 `Commit`
- 手动执行 `Push`
- 查看最近提交记录
- 按 `全部分支 / 当前分支 / 其他本地分支` 筛选 Commit 记录
- 切换到历史提交版本，并支持从 detached HEAD 恢复
- 查看运行日志
- 快速打开 `.gitignore`
- 在当前目录执行 `git init`

## 不做什么

- 不会自动创建 GitHub 仓库
- 不会自动下载依赖或安装 Git
- 不会自动替你生成 `.gitignore` 内容
- 不会自动帮你完成 GitHub 登录认证
- 不会自动执行 `pull`、`merge`、`rebase`

## 启动方式

### 用 Python 直接运行

```powershell
python git_auto_commit_gui.py
```

### 运行打包好的 EXE

```text
dist/GitAutoCommitTool.exe
```

建议先自己新建一个专门的工具文件夹，再把 `GitAutoCommitTool.exe` 放进去运行，例如：

```text
D:\Tools\GitAutoCommitTool\
```

程序运行后，会把配置文件和日志文件默认放在 `exe` 所在目录，方便一起备份和迁移。

## 使用流程

1. 选择一个本地项目文件夹
2. 如果它还不是 Git 仓库，可以先点 `git init`
3. 按需要填写 GitHub 地址、Git 用户名和邮箱
4. 需要自动留快照时，打开 `Auto Commit` 并设置间隔
5. 需要立即整理提交时，点击 `Commit`
6. 需要同步到远程时，点击 `Push`

## 手动 Commit 说明

点击 `Commit` 后，会打开一个和主界面风格一致的手动提交窗口：

- 左侧填写标题
- 标题前可以选择常见的 Commit 前缀，例如 `fix`、`feat`、`perf`、`refactor`
- 也可以切换到 `自定义` 后输入自己的前缀
- 右侧内容区可选，用来补充这次改动的详细说明

手动提交消息会按下面这种结构生成：

```text
fix: 修复手动提交后列表不刷新的问题

补充说明可以写在这里，作为 commit body 保存。
```

如果当前没有新的文件改动，但仓库里已经存在最近一次提交，手动 `Commit` 不会再提示“无修改不能提交”，而是把最近一次提交改名为你这次填写的新标题和内容。

## Auto Commit 说明

开启后，程序会按你设置的时间间隔执行以下逻辑：

1. 执行 `git add -A`
2. 检查是否真的存在暂存改动
3. 有改动时再执行 `git commit`

自动生成的提交信息格式类似：

```text
auto snapshot 12 2026-06-28 16:30:00
```

说明：

- 没有新改动时，不会产生空提交
- 遇到 Git 正在 `merge`、`rebase`、`cherry-pick` 等占用状态时，会跳过本轮自动提交
- `Auto Commit` 默认只做本地提交，不会自动推送到 GitHub

## Commit 记录说明

`Commit 记录` 右上角可以直接切换查看范围：

- `全部分支`
- `当前分支：xxx`
- 其他本地分支

这样既可以从全局看历史，也可以只看当前开发线，避免不同分支的记录混在一起时不容易判断。

## Push 说明

- 如果你填写了 GitHub 地址，但仓库还没有 `origin`，程序会自动帮你添加
- 如果 `origin` 已存在但地址不同，程序会自动更新
- 第一次 `push` 可能会要求你先在本机完成 GitHub 认证
- 如果当前处于 detached HEAD，程序会尽量先创建一个恢复分支，再继续推送

## 配置文件和日志

程序默认会把下面这些文件放在工具目录里：

- `git_auto_commit_gui_config.json`
- `git_auto_commit_gui.log`

这意味着：

- 你把整个工具目录复制给别人时，程序、配置和日志会放在一起
- 你自己备份或迁移工具时更方便
- 重新放到新的目录后，也更容易定位配置文件

## 常见问题

### 1. 点了 Commit 没反应

可能原因：

- 当前没有新的改动，程序会改名最近一次提交，而不是新建空提交
- 当前仓库还没有任何历史提交，且这次也没有新改动
- 标题没有填写，程序会阻止提交

### 2. Push 失败

常见原因：

- 远程仓库比本地更新，需要先 `pull`
- GitHub 认证还没完成
- 当前仓库权限不足
- 当前目录不是安全目录，需要手动加入 `safe.directory`

### 3. 选择了文件夹却提示不是 Git 仓库

说明这个目录下还没有 `.git` 文件夹。你可以先点 `git init`，或者确认自己没有选错目录。

## 重新打包 EXE

如果你要重新生成可执行文件：

```powershell
pip install -r requirements-build.txt
python -m PyInstaller GitAutoCommitTool.spec
```

打包结果默认在 `dist/` 目录。

## 使用建议

- 第一次建议先拿测试仓库试一遍完整流程
- 自动提交虽然方便，但不等于备份系统，重要项目仍建议及时 `push`
- 如果项目里有编译产物、缓存文件或大文件，建议先写好 `.gitignore`
