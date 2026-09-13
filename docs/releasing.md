# 版本与发布

仓库用一个语义化版本号（`MAJOR.MINOR.PATCH`）标记 skill、辅助脚本和课程库的整体状态。
版本号只写在根目录的 `VERSION` 里；Git tag、GitHub Release 和已安装 skill 记录的版本都由它派生。

## 版本号怎么升

| 这次合并带来的变化 | 升哪一位 | 例子 |
|---|---|---|
| 已有用法需要跟着改：辅助脚本删改了参数、工作目录产物改了格式，或者原本能通过 `verify_notes.py` 的工作目录现在通不过 | MAJOR | 删除 `frame_filter.py crop --bands`；交付检查新增必填产物 |
| 新增能力，旧用法不受影响；新增课程或讲次 | MINOR | 新增 `layout` 子命令；上线一门新课 |
| 修正错误、改文档、勘误已发布内容 | PATCH | 修一处裁剪越界；更正讲义封面讲次 |

一次发布包含多种变化时，按最高的一位升级，低位清零（`1.4.2` → `2.0.0`）。

## 发布步骤

1. 在准备发布的 PR（可以就是最后一个功能 PR）里：
   - 把 `VERSION` 改成新版本号；
   - 在 `RELEASE_NOTES.md` 顶部加一节 `## vX.Y.Z — YYYY-MM-DD — 标题`，写这一版改变了什么、
     有哪些兼容性影响。GitHub Release 页面只显示这一节，所以要能单独读懂。
2. 本地确认版本号和发布说明一致：

   ```bash
   python3 scripts/release_notes.py check
   ```

   单元测试也会跑这项检查，改了 `VERSION` 却没写对应小节，PR 的 `unit` 检查会失败。
3. PR 合并后，在最新的 `main` 上打带注释的 tag 并推送：

   ```bash
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

4. 推送 tag 会触发 `.github/workflows/release.yml`，依次执行：
   - 核对 tag、`VERSION` 和 `RELEASE_NOTES.md` 三者一致；
   - 确认 tag 指向的提交已经在 `main` 上；
   - 在该提交上跑全部 Python 测试；
   - 用该版本的小节创建 GitHub Release。

   任何一步失败都不会创建 Release。修正后删除远端 tag（`git push origin :refs/tags/vX.Y.Z`），
   再从第 3 步重来。

## 查看已安装 skill 的版本

`scripts/install_skill.sh` 会在安装目录的 `assets/INSTALLED_FROM` 里写入 `version=`（来自
`VERSION`）和 `commit=`（安装时的提交）。反馈问题时附上这两行，维护者就能对应到具体版本。
