# KYMol 0.3.0 安装与使用

## 安装

1. 从 GitHub Releases 下载 `KYMol-0.3.0.zip`，不要解压。
2. 在 PyMOL 中打开 `Plugin > Plugin Manager > Install New Plugin`。
3. 选择下载的 ZIP 文件。
4. 完全退出并重新启动 PyMOL。
5. 打开 `Plugin > KYMol: Structure Review Panel`。

如果插件已成功加载，PyMOL 控制台会显示：

```text
[KYMol] v0.3.0 loaded. Open Plugin > KYMol: Structure Review Panel.
```

如果以前安装过 `KYPyMol`，建议先卸载旧版本，避免菜单重复。

## 面板工作方式

- 在 KYMol 对象列表中按住 `Ctrl` 或 `Shift` 选择一个或多个对象。
- 最后点中的已选对象显示为金色，它是当前活动目标。
- 普通点击和拖动用于文件夹整理；只有按住 `Ctrl` 或 `Shift` 时才改变多选。
- PyMOL 主窗口只负责三维显示，选择和批量操作以 KYMol 面板中的状态为准。

## 常用快捷键

| 快捷键 | 功能 |
|---|---|
| `Shift+Alt+A` | 将其他已选对象对齐到金色活动目标 |
| `Alt+A` | PyMOL 全局对齐备用快捷键 |
| `Alt+C` | 按链着色 |
| `H` | 隐藏选中对象或当前文件夹 |
| `Alt+H` | 显示全部分子对象 |
| `/` | 独显选中对象或当前文件夹 |
| `M` | 创建原生 PyMOL 分组 |
| `F2` | 重命名活动对象 |
| `X` / `Delete` | 确认后删除选中对象 |

## 分组

选择对象后按 `M`。KYMol 会给出 `P1`、`P2`、`P3` 等不重复的默认名称，也可手动修改。对象可直接拖到分组中；双击分组可选择其中全部分子对象。

这些分组是 PyMOL 原生分组，保存到 `.pse` 后，其他用户即使没有安装 KYMol 也能正常打开。

## 限制

PyMOL 原生对象树没有可靠公开的“最后点击对象”接口，因此金色活动目标必须在 KYMol 面板中确定。删除对象后如需恢复，请重新载入原始 PDB/CIF 文件。
