# Windows 启动程序品牌更新

入口改为 `Think Aloud.exe`，使用现有 `ui/brand.ico` 的砖红引号与书签图形；
文件说明、产品名、原始文件名和版本资源同步更新。窗口的现有图标不变。

## 已验证

- 98 项相关测试通过：原生启动器 2 项、打包/安装/发布准备 86 项、更新器 10 项。
  初次组合运行额外出现 1 个测试模块导入路径错误；补充 tests 搜索路径后，
  单独运行剩余的更新器 10 项通过。这不是应用运行失败。
- 实际 Win32 资源读取验证各尺寸图标与源 ICO 一致、原始 PE manifest 保留，
  产品名/说明/版本可由 Windows 版本 API 读取；重复构建字节一致。
- 从无关工作目录启动带中文和空格路径下的新 EXE，实际进入旁边的私有 Python。
- Windows `ExtractAssociatedIcon` 真实提取图标，人工查看确认为已有品牌标识。
- 升级事务测试覆盖旧入口到新入口、下一次新入口更新、失败回滚、同名个人文件
  冲突、未登记启动程序、被篡改启动程序，以及配置保持不变。
- 独立只读工程审查未发现阻塞项。

本地安装验收时发现，旧普通 `--self-check` 在安装目录改名后会触发配置迁移。
已将普通自检改为只读；只有显式请求合成录制验收才初始化配置。新增 3 项自检
测试及 4 项既有预设测试通过，相关检查合计 105 项。Windows 临时目录短文件名
与展开路径差异曾导致 1 个测试期望失败，改为比较解析后的路径后通过。

本机 `D:\Think Aloud` 已安装 `0.6.0-preview.5+local.3`。最终事务位于
`D:\Think Aloud backups\20260923-launcher-branding\transaction-v2`，实际新旧 EXE
均通过自检；14 个配置/密钥/词库/布局文件与本轮备份一致。旧入口仅隐藏，字节
保持不变，旧快捷方式继续有效；本机恢复脚本会恢复旧入口可见性。
发生自检迁移后，精确配置已从本轮备份恢复，OBS 配置从上一轮保留的配置恢复，
场景取最近的 OBS `.bak`；恢复来源单独记录，没有把旧备份称为本轮完整快照。
修正后的新旧入口自检均确认未再次改动配置和这 6 个 OBS 文件。

## 兼容边界

新安装器支持旧包，不代表旧安装器能接受新包。旧预览版的根目录 EXE 白名单
拒绝新名称；首次手动过渡或先提供过渡版本的规则见 [软件更新](updates.md)。
没有变更 GitHub 附件命名，没有推送或发布。

实现依据：[UpdateResourceW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-updateresourcew)
与 [VS_VERSIONINFO](https://learn.microsoft.com/en-us/windows/win32/menurc/vs-versioninfo)。
资源写入先作用于临时 PE，成功后才追加相对 shebang 与 Python ZIP。
