# Source/Logic/Core.py
# -*- coding: utf-8 -*-

import os
import uuid
import subprocess

# ================== Low-Level Wrapper ==================

def RunCmd(Command, InputText=None):
    """
    同步运行外部命令。
    返回 subprocess.CompletedProcess（含 returncode / stdout / stderr）。
    """
    return subprocess.run(
        Command,
        input=(InputText or ""),
        capture_output=True,
        text=True
    )

class P4Context:
    """
    封装 p4 命令的上下文（Server/User/Client/Password）。
    所有 p4 调用统一通过此上下文发起，确保可在多服务器/多工作区之间切换。
    """
    def __init__(self, Server:str="", User:str="", Client:str="", Password:str=""):
        self.Server   = Server
        self.User     = User
        self.Client   = Client
        self.Password = Password

    def Build(self, ExtraArgs):
        """
        构建完整的 p4 命令行（自动注入 -p/-u/-c）。
        """
        Cmd = ["p4"]
        if self.Server: Cmd += ["-p", self.Server]
        if self.User:   Cmd += ["-u", self.User]
        if self.Client: Cmd += ["-c", self.Client]
        Cmd += ExtraArgs
        return Cmd

    def Exec(self, ExtraArgs, InputText=None):
        """
        执行 p4 命令。
        """
        return RunCmd(self.Build(ExtraArgs), InputText=InputText)

    def LoginIfNeeded(self) -> bool:
        """
        如提供 Password，则尝试非交互登录；否则直接返回 True。
        """
        if not self.Password:
            return True
        R = self.Exec(["login", "-a"], InputText=self.Password + "\n")
        return R.returncode == 0

    def TestConnection(self):
        """
        测试连接：执行 `p4 info`。
        返回 (ok:bool, message:str)
        """
        R = self.Exec(["info"])
        return (R.returncode == 0, (R.stdout + R.stderr))

# ================== Core Helpers ==================

def DepotBaseName(DepotPath:str) -> str:
    """
    从 depot 路径获取文件名（不含目录）。
    例如 //depot/Path/File.cpp -> File.cpp
    """
    return DepotPath.rsplit("/", 1)[-1]

def LocalBaseName(LocalPath:str) -> str:
    """
    从本地路径获取文件名（不含目录）。
    例如 D:/Work/File.cpp -> File.cpp
    """
    return os.path.basename(LocalPath)

def NormalizeChangelist(Changelist:str) -> str:
    """
    归一化 Changelist 字段：空字符串都视为 'default'。
    """
    return Changelist.strip() if Changelist and Changelist.strip() else "default"

# ================== Query Opened Files ==================

def GetOpenedPairs(P4:P4Context, Changelist:str, Log=lambda s:None):
    """
    获取目标 changelist 中的已打开文件，返回列表 [(DepotPath, LocalPath)]。
    通过 `p4 opened -c <cl>` + `p4 where <depot>` 映射本地路径。
    """
    Cl = NormalizeChangelist(Changelist)
    Args = ["opened", "-c", Cl]
    O = P4.Exec(Args)
    if O.returncode != 0:
        Log(O.stderr or O.stdout)
        return []

    Pairs = []
    for Line in O.stdout.splitlines():
        if "//" not in Line:
            continue
        DepotPath = Line.split("#")[0].strip()
        W = P4.Exec(["where", DepotPath])
        if W.returncode != 0:
            Log(W.stderr or W.stdout)
            continue
        Parts = W.stdout.strip().split()
        # 典型输出: //<depot> //<client> <localpath>
        if len(Parts) >= 3:
            LocalPath = Parts[-1]
            Pairs.append((DepotPath, LocalPath))
    return Pairs

# ================== Rename Strategies ==================

def TrySingleMove(LocalSrc:str, LocalDst:str, P4:P4Context, Log=lambda s:None) -> bool:
    """
    尝试一次 `p4 move LocalSrc LocalDst`。
    成功返回 True，失败返回 False 并记录日志。
    """
    R = P4.Exec(["move", LocalSrc, LocalDst])
    if R.returncode != 0:
        Log(R.stderr or R.stdout)
        return False
    return True

def TwoStepMove(LocalSrc:str, LocalDst:str, P4:P4Context, Log=lambda s:None) -> bool:
    """
    两步改名（临时名 -> 目标名），用于大小写不敏感文件系统/服务器：
      1) p4 move LocalSrc TmpPath
      2) p4 move TmpPath LocalDst
    """
    BaseDst = os.path.basename(LocalDst)
    TmpPath = os.path.join(os.path.dirname(LocalDst), f"__TMP__{uuid.uuid4().hex}_{BaseDst}")

    R1 = P4.Exec(["move", LocalSrc, TmpPath])
    if R1.returncode != 0:
        Log(R1.stderr or R1.stdout)
        return False

    R2 = P4.Exec(["move", TmpPath, LocalDst])
    if R2.returncode != 0:
        Log(R2.stderr or R2.stdout)
        return False

    return True

# ================== Main Operation ==================

def SyncDepotCaseToLocal(P4:P4Context,
                         Changelist:str,
                         DryRun:bool,
                         Log=lambda s:None,
                         Progress:dict|None=None) -> int:
    """
    以**本地磁盘的真实文件名**为准，修正 depot 路径的大小写。
    流程：
      - 枚举 changelist 已打开文件
      - 若 depot 文件名与本地文件名大小写不一致：
          先尝试一次 move；失败则两步 move
      - DryRun=True 时不实际改动，仅统计/打印
    Progress 可传入 {"SetTotal": callable, "Step": callable} 用于更新进度条。
    返回修改数量（需要修正且成功通过策略的文件数；DryRun 时即为检测到的不一致个数）。
    """
    Pairs = GetOpenedPairs(P4, Changelist, Log)
    Total = len(Pairs)
    if Progress and "SetTotal" in Progress and callable(Progress["SetTotal"]):
        Progress["SetTotal"](Total)

    if not Pairs:
        Log("No opened files in the changelist.")
        return 0

    Changed = 0
    Processed = 0

    for DepotPath, LocalPath in Pairs:
        LocalName = LocalBaseName(LocalPath)
        DepotName = DepotBaseName(DepotPath)

        # 本地文件不存在（被删/移动等），跳过但推进进度
        if not os.path.exists(LocalPath):
            Processed += 1
            if Progress and "Step" in Progress and callable(Progress["Step"]):
                Progress["Step"](Processed)
            continue

        # 大小写一致则跳过
        if LocalName == DepotName:
            Processed += 1
            if Progress and "Step" in Progress and callable(Progress["Step"]):
                Progress["Step"](Processed)
            continue

        # 目标路径为“本地真实文件名”
        TargetPath = os.path.join(os.path.dirname(LocalPath), LocalName)
        Log(f"[CaseFix] {DepotName}  ->  {LocalName}")

        if DryRun:
            Changed += 1
        else:
            # 先尝试单步 move；失败再两步
            if TrySingleMove(LocalPath, TargetPath, P4, Log):
                Changed += 1
            elif TwoStepMove(LocalPath, TargetPath, P4, Log):
                Changed += 1
            else:
                Log(f"[Error] Failed to rename: {LocalPath}")

        # 进度推进
        Processed += 1
        if Progress and "Step" in Progress and callable(Progress["Step"]):
            Progress["Step"](Processed)

    return Changed

# ================== Submit ==================

def SubmitChange(P4:P4Context, Changelist:str, Description:str, Log=lambda s:None) -> bool:
    """
    提交指定 changelist。
    - 若 Description 非空，则使用 `p4 submit -d <desc> [-c <cl>]`
    - 否则使用交互/表单（由 p4 配置决定）
    返回是否提交成功。
    """
    Cl = NormalizeChangelist(Changelist)
    if Description:
        Args = ["submit", "-d", Description]
        if Cl != "default":
            Args += ["-c", Cl]
    else:
        Args = ["submit"]
        if Cl != "default":
            Args += ["-c", Cl]

    R = P4.Exec(Args)
    Log(R.stdout)
    if R.returncode != 0:
        Log(R.stderr or "")
        return False
    return True
