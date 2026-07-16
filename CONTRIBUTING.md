# 提交课程 PDF

普通贡献者不能直接向 `ysyecust/lecture-to-notes` 的 `main` 分支写入文件。
正确流程是：

```text
贡献者自己的 Fork  →  Pull Request  →  维护者审核并合并  →  网站发布
      commit              请求合并             写入 main
```

- **仓库所有者或有 Write 权限的协作者**可以直接 push。为了保留检查和审核记录，
  课程资料仍建议通过分支和 Pull Request 提交。
- **普通贡献者**在自己的 Fork 中 commit。他们提交 Pull Request 后，仍然没有
  原仓库的写入权限。
- **自动检查**只负责检查文件和生成报告，不会自动合并 Pull Request。
- **维护者**决定合并、要求修改或关闭 Pull Request。只有合并后的内容会发布。

如果你第一次使用 GitHub，请按下面的网页步骤操作。GitHub 官方也提供了
[Fork 说明](https://docs.github.com/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo)
和 [从 Fork 创建 Pull Request 的说明](https://docs.github.com/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork)。

## 方法一：在 GitHub 网页提交

### 1. Fork 仓库

1. 登录 GitHub，打开 <https://github.com/ysyecust/lecture-to-notes>。
2. 点击右上角 **Fork**。
3. 点击 **Create fork**。GitHub 会在你的账号下创建仓库副本：
   `https://github.com/<你的账号>/lecture-to-notes`。

你接下来创建的 commit 都在这个副本中，不会直接改变本站仓库。

### 2. 上传 PDF

1. 在你的 Fork 中打开 `content/inbox/`。
2. 点击 **Add file → Upload files**。
3. 选择要提交的 PDF。文件必须直接放在 `content/inbox/` 下，不要再建子目录。
4. 不要在同一个 Pull Request 中修改代码、课程清单或现有文件。

### 3. 保存 commit

在 **Commit changes** 窗口中：

1. 填写简短说明，例如 `content: add CS336 lecture notes`。
2. 建议选择 **Create a new branch for this commit and start a pull request**。
3. 如果 GitHub 只提供提交到你自己的 `main`，也可以继续；这是你的 Fork 的
   `main`，不是 `ysyecust/lecture-to-notes` 的 `main`。
4. 点击 **Commit changes**。

### 4. 创建 Pull Request

1. 回到你的 Fork 首页，点击 **Contribute → Open pull request**。
2. 检查页面顶部的目标和来源：
   - base repository：`ysyecust/lecture-to-notes`
   - base branch：`main`
   - head repository：`<你的账号>/lecture-to-notes`
   - compare branch：刚才保存 commit 的分支
3. 选择 **PDF contribution** 模板。
4. 填写课程信息并勾选全部确认项。
5. 点击 **Create pull request**。

Pull Request 是“请求合并”，不是把仓库写权限交给贡献者。贡献者后续如果需要
修改文件，只需继续向自己 Fork 中的同一分支 push，Pull Request 会自动更新。

## 方法二：使用命令行提交

先在 GitHub 上 Fork 仓库，再运行：

```bash
git clone https://github.com/<你的账号>/lecture-to-notes.git
cd lecture-to-notes
git remote add upstream https://github.com/ysyecust/lecture-to-notes.git
git switch -c contribute/<课程简称>
cp /本地路径/lecture.pdf content/inbox/
git add content/inbox/lecture.pdf
git commit -m "content: add <课程名称> lecture notes"
git push -u origin contribute/<课程简称>
```

然后打开你的 Fork，点击 **Compare & pull request**，目标选择
`ysyecust/lecture-to-notes:main`，再填写 **PDF contribution** 模板。

## Pull Request 需要填写什么

模板会要求以下信息：

- 课程或活动名称
- 学校或机构
- 学期或年份
- 讲次或主题
- 讲师
- 原始来源 URL
- 文件之间的关系，例如“前三讲分讲 PDF + 合集”
- 其他需要维护者知道的说明

来源信息不完整时，请说明哪些内容无法确认，不要猜测。

## 文件要求

- 每个 Pull Request 添加 1–10 个 PDF。
- 单个 PDF 不超过 25 MiB。
- 一个 Pull Request 内的 PDF 合计不超过 100 MiB。
- 文件扩展名必须是小写 `.pdf`。
- 文件必须直接放在 `content/inbox/` 下。
- 不要提交符号链接、压缩包、脚本，也不要修改或删除现有文件。
- 只提交你有权用于教育用途分享的资料。

这些限制只用于控制外部 Pull Request 的自动检查规模，不是网站课程数量或仓库总容量的上限。

## 提交后会发生什么

自动检查会：

1. 确认 Pull Request 只添加了允许的 PDF。
2. 在断网、只读、非 root 的容器中检查 PDF 结构和活动内容。
3. 解析标题和页数，计算 SHA-256，并生成第一页 WebP 预览。
4. 把报告放在 Pull Request 的 GitHub Actions 运行记录中。

维护者审核来源和内容后，可以直接合并为“社区贡献”，也可以另行调整文件名、
课程归属和课程清单。未合并的 Pull Request 不会发布到网站。
