# P4CaseSync

**P4CaseSync** 是一个在 **Perforce 提交前**同步修正**文件路径与文件名大小写**的小工具。  
在 Windows 下，P4 常把大小写“弱化”，导致上传后目录与文件被小写化。本工具会依据**本地磁盘真实大小写**对 `p4 opened` 中的文件进行纠正，并可手动微调，再一键应用为 `p4 move`。

## ✨ 功能特性
- 扫描 Changelist（或 default）中的已打开文件
- 使用 `p4 where` 映射并读取**本地真实大小写**，支持整条路径逐级纠正
- 列表颜色区分（直观辨识）  
  - **灰色**：更改前后完全一致（无需修改）  
  - **绿色**：与“自动修正值”一致（自动处理）  
  - **红色**：用户手动修改，与自动值不一致  
- 双击**整行**弹出编辑框（居中显示）
- 应用修改后做**一致性检测**；不一致自动尝试“双步 move 回退法”，仍不一致判失败
- 仅显示 `edit / add / move/add`，自动隐藏删除类动作

## 🖼 界面提示
- 顶部有**颜色说明**与“仅显示需要修改的文件”开关  
- 列表行显示“更改前 / 更改后”，双击行可编辑“更改后”

## 🔧 运行环境
- Windows（推荐）  
- Python 3.8+  
- 已安装 **Perforce CLI** `p4`（命令行需要可用）  
- Tkinter（Python 自带）  
- （开发/打包选用）PyInstaller

---

## 🚀 快速开始

### 1) 克隆并进入目录
```bash
git clone https://github.com/<your-org-or-user>/P4CaseSync.git
cd P4CaseSync
```

### 2) 安装依赖（二选一）

#### A. 使用 Miniconda / Anaconda（推荐）
```bash
# 新建环境（示例用 python 3.11）
conda create -n p4casesync python=3.11 -y
conda activate p4casesync

# 安装打包所需（运行本工具本身无需第三方包；打包需要 PyInstaller）
pip install -r requirements.txt
# 如果你没有 requirements.txt，可先： pip install pyinstaller
```

#### B. 使用内置 venv + pip
```bash
# Windows PowerShell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> 说明：项目运行仅依赖标准库与 `p4` 命令；`requirements.txt` 一般只需要记录 `pyinstaller`（用于打包）。  
> 如果你没有该文件，可创建一个只包含：  
> ```
> pyinstaller>=6
> ```

### 3) 运行
```bash
# 在激活环境下
python Main.py
```

---

## 📦 打包（生成单文件 EXE）

本项目使用动态路径导入，需要通过 **spec 文件**指定隐藏导入。

### 推荐方式（使用 spec 文件）

```bash
pyinstaller P4CaseSync.spec
```

生成的 exe 位于 `dist/P4文件名大小写同步工具.exe`

### spec 文件说明

`P4CaseSync.spec` 已配置：
- 单文件打包（`--onefile`）
- 无控制台窗口（`--noconsole`）
- 隐藏导入模块：`LoginUI`, `MainUI`, `Core`
- 输出文件名：`P4文件名大小写同步工具`

如需修改配置（如文件名、图标），编辑 `P4CaseSync.spec` 文件：
- 修改名称：找到 `name='P4文件名大小写同步工具'` 这行
- 添加图标：将 `icon=None` 改为 `icon='icon.ico'`
- 显示控制台：将 `console=False` 改为 `console=True`（用于调试）

### ⚠️ 注意事项

**不要使用**命令行参数与 spec 文件混用：
```bash
# ❌ 错误示例
pyinstaller -F -w P4CaseSync.spec  # 会报错

# ✅ 正确用法
pyinstaller P4CaseSync.spec
```

### 为什么需要 spec 文件？

本项目使用 `InjectSysPath()` 动态添加模块路径，PyInstaller 无法自动识别 `Source/UI` 和 `Source/Logic` 下的模块。spec 文件通过 `hiddenimports` 参数显式声明这些模块，确保打包成功。

---

## 🧭 使用步骤
1. 打开工具，选择需要处理的 **Changelist**（默认 `default`）。  
2. 工具自动列出文件：  
   - **灰色**：更改前后相同，跳过  
   - **绿色**：自动按本地真实大小写修正  
   - **红色**：你手动修改过且与自动值不同  
3. 如需调整，双击行，在弹窗中修改“更改后”路径。  
4. 点击 **应用修改**：会依次 `p4 move`，并进行一致性复核；必要时使用“双步 move 回退法”。  
5. 在 P4V 或命令行正常提交。

---

## ❓常见问题（FAQ）

**Q1: 为什么显示“灰色大条”或残影？**  
A: 已修复。刷新列表时我们会销毁所有子控件（含分隔线），避免残留。

**Q2: 为什么有时显示“X”而不是“✔”？**  
A: 取决于系统主题。我们优先使用 Windows 的 `vista/xpnative` 主题。若仍不满意，可换自定义图标方案。

**Q3: 本地路径不存在怎么办？**  
A: 会尽可能纠正到能访问到的最深父目录，无法纠正的部分保持原样，并允许手动编辑。

**Q4: 提交动作里包含删除怎么办？**  
A: 我们默认**过滤**删除类动作（`delete/move/delete`），只显示 `edit/add/move/add`。

---

## 🧪 开发者提示
- 颜色规则判断（最终版）：  
  1) 更改后 == 更改前 → 灰  
  2) 更改后 != 更改前 且 更改后 == 自动值 → 绿  
  3) 更改后 != 自动值 → 红  
- 双击**整行**弹出编辑框；编辑后立即刷新颜色  
- 一致性校验失败 → 自动尝试双步移动（临时名 → 目标名）再校验

---

## 🧰 导出与还原环境

> 你说的“minicode 虚拟环境”，一般是 **Miniconda**。下面分别给出 **Conda** 与 **pip/venv** 两套方案。

### 方案 A：Conda（Miniconda/Anaconda）

**导出（推荐从历史，避免把无关包写进去）：**
```bash
# 当前激活 p4casesync 环境
conda env export > environment.yml
```

**还原：**
```bash
conda env create -f environment.yml
conda activate p4casesync
```

### 方案 B：pip + venv

**导出：**
```bash
# 激活你的 venv 后
pip freeze > requirements.txt
```

**还原：**
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 📄 许可证
MIT License

---

## 🙌 致谢
感谢所有使用与反馈 **P4CaseSync** 的开发者。遇到问题欢迎提 Issue，或提交 PR 参与改进。
