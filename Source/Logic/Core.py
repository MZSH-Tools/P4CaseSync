# Core.py
# -*- coding: utf-8 -*-
import subprocess
import os
from typing import List, Tuple

class P4Context:
    """
    封装 p4 命令调用的上下文（Server/User/Client）。
    提供 Exec, Test, Login 方法。
    """
    def __init__(self, Server: str, User: str, Client: str):
        self.Server = Server
        self.User   = User
        self.Client = Client

    def Exec(self, Args: List[str]) -> subprocess.CompletedProcess:
        """
        执行 p4 命令，返回 CompletedProcess。
        """
        Cmd = ["p4", "-p", self.Server, "-u", self.User, "-c", self.Client] + Args
        return subprocess.run(Cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    def Test(self) -> Tuple[bool, str]:
        """
        测试当前连接是否可用。
        """
        R = self.Exec(["info"])
        Ok = R.returncode == 0
        return Ok, (R.stderr or R.stdout or "").strip()

    def Login(self, Password: str) -> Tuple[bool, str]:
        """
        使用密码登录。
        """
        Cmd = ["p4", "-p", self.Server, "-u", self.User, "login"]
        P = subprocess.Popen(Cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = P.communicate(Password + "\n")
        Ok = P.returncode == 0
        return Ok, (err or out or "").strip()


# -------- Changelist 列表 --------
def ListPendingChangelists(Ctx: P4Context) -> List[str]:
    """
    列出当前用户在当前工作区的 pending changelists（含 'default'）。
    """
    Items = ["default"]
    R = Ctx.Exec([
        "changes", "-s", "pending",
        "-c", Ctx.Client,
        "-u", Ctx.User
    ])
    if R.returncode == 0:
        for Line in (R.stdout or "").splitlines():
            Parts = Line.strip().split()
            if len(Parts) >= 2 and Parts[0].lower() == "change":
                Items.append(Parts[1])
    return Items


# -------- 获取文件列表 --------
def GetOpenedPairs(Ctx: P4Context, Changelist: str) -> List[Tuple[str, str]]:
    """
    获取指定 Changelist 中的 depot 路径与本地路径。
    返回 [(DepotPath, LocalPath), ...]
    """
    if not Changelist or Changelist.lower() == "default":
        Args = ["opened"]
    else:
        Args = ["opened", "-c", Changelist]

    R = Ctx.Exec(Args)
    if R.returncode != 0:
        return []

    Result: List[Tuple[str, str]] = []
    for Line in (R.stdout or "").splitlines():
        Parts = Line.strip().split()
        if not Parts:
            continue
        DepotPath = Parts[0]
        # 获取本地路径
        Where = Ctx.Exec(["where", DepotPath])
        if Where.returncode != 0:
            continue
        # p4 where 输出形如：//depot/path/file //client/path/file C:\local\path\file
        WParts = Where.stdout.strip().split()
        if len(WParts) >= 3:
            LocalPath = WParts[-1]
            Result.append((DepotPath, LocalPath))
    return Result


# -------- 文件名规范化 --------
def NormalizeName(LocalPath: str) -> str:
    """
    根据本地路径生成规范化文件名（示例：大小写修正）。
    当前简单返回 basename，可自行扩展规则。
    """
    return os.path.basename(LocalPath)


# -------- 改名实现 --------
def TrySingleMove(Ctx: P4Context, SrcDepot: str, DstDepot: str) -> bool:
    """
    单步 p4 move 尝试改名。
    """
    R = Ctx.Exec(["move", SrcDepot, DstDepot])
    return R.returncode == 0

def TryTwoMoves(Ctx: P4Context, SrcDepot: str, DstDepot: str) -> bool:
    """
    先改到临时名再改回目标名（解决大小写不敏感系统的 p4 move 问题）。
    """
    Dir = os.path.dirname(DstDepot)
    Base = os.path.basename(DstDepot)
    TempName = f"{Base}.__tmp__"
    TempDepot = f"{Dir}/{TempName}" if Dir else f"/{TempName}"
    TempDepot = TempDepot.replace("//", "/")

    R1 = Ctx.Exec(["move", SrcDepot, TempDepot])
    if R1.returncode != 0:
        return False
    R2 = Ctx.Exec(["move", TempDepot, DstDepot])
    return R2.returncode == 0
