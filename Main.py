# Main.py
# -*- coding: utf-8 -*-

import os
import sys

def InjectSysPath():
    BaseDir  = os.path.dirname(os.path.abspath(__file__))
    UiDir    = os.path.join(BaseDir, "Source", "UI")
    LogicDir = os.path.join(BaseDir, "Source", "Logic")
    for P in (UiDir, LogicDir):
        if P not in sys.path:
            sys.path.insert(0, P)

def NeedsPassword(Msg: str) -> bool:
    S = (Msg or "").lower()
    return ("password invalid" in S) or ("p4passwd" in S and "invalid" in S) or ("unset" in S and "password" in S)

def BuildTargetDepot(DepotPath: str, TargetName: str) -> str:
    DirDepot = os.path.dirname(DepotPath).replace("\\", "/")
    T = f"{DirDepot}/{TargetName}" if DirDepot else f"/{TargetName}"
    T = T.replace("//", "/")
    if not T.startswith("//"):
        T = "/" + T.lstrip("/")
        if not T.startswith("//"):
            T = "/" + T  # 保底，确保以 // 开头
    return T

def Main():
    InjectSysPath()

    # 延迟导入以便 sys.path 生效
    from AppUI import AppUI
    from Core import P4Context, GetOpenedPairs, NormalizeName, TrySingleMove, TryTwoMoves

    App = AppUI()

    # ---- 由 Main 持有的运行时状态 ----
    Ctx = {"P4": None}

    # ---- 回调：登录/连接 ----
    def OnConnected(Server: str, User: str, Client: str, PasswordOrNone):
        P4 = P4Context(Server, User, Client)

        Ok, Msg = P4.Test()
        if not Ok:
            # 若需要密码，借用 LoginFrame 的弹窗
            if NeedsPassword(Msg):
                Prompt = getattr(App.CurrentFrame, "PromptPassword", None)
                Password = Prompt() if callable(Prompt) else None
                if not Password:
                    App.ShowError("需要密码，但未提供。")
                    return
                OkLogin, MsgLogin = P4.Login(Password)
                if not OkLogin:
                    App.ShowError(f"登录失败：\n{MsgLogin or ''}".strip())
                    return
                Ok, Msg = P4.Test()

        if not Ok:
            App.ShowError(Msg or "连接失败")
            return

        # 连接成功：保存上下文并切换到主界面
        Ctx["P4"] = P4
        App.SwitchToMain()
        # 初次刷新
        OnRefresh("default")

    # ---- 回调：刷新列表 ----
    def OnRefresh(Changelist: str):
        if not Ctx["P4"]:
            App.ShowError("尚未连接到 Perforce。")
            return
        try:
            Pairs = GetOpenedPairs(Ctx["P4"], Changelist or "default")  # [(DepotPath, LocalPath)]
            Targets = [NormalizeName(LocalPath) for _, LocalPath in Pairs]
            App.RenderPairs(Pairs, Targets)
        except Exception as Ex:
            App.ShowError(f"刷新失败：{Ex}")

    # ---- 回调：应用改名 ----
    def OnApply(Indices, Pairs, Targets):
        if not Ctx["P4"]:
            App.ShowError("尚未连接到 Perforce。")
            return

        OkCount, FailCount = 0, 0
        Logs = []

        for I in Indices:
            Depot, _Local = Pairs[I]
            if not isinstance(Depot, str) or not Depot.startswith("//"):
                Logs.append(f"[跳过] 非法 depot: {Depot}")
                continue

            Target = Targets[I]
            TargetDepot = BuildTargetDepot(Depot, Target)

            try:
                if TrySingleMove(Ctx["P4"], Depot, TargetDepot) or TryTwoMoves(Ctx["P4"], Depot, TargetDepot):
                    OkCount += 1
                    Logs.append(f"[OK] {Depot} -> {TargetDepot}")
                else:
                    FailCount += 1
                    Logs.append(f"[FAIL] {Depot} -> {TargetDepot}")
            except Exception as Ex:
                FailCount += 1
                Logs.append(f"[EXC]  {Depot} -> {TargetDepot} : {Ex}")

        App.ShowResult(OkCount, FailCount, Logs[-50:])

    # ---- 将回调绑定到 UI ----
    App.BindHandlers(
        OnConnected=OnConnected,
        OnRefresh=OnRefresh,
        OnApply=OnApply,
    )

    App.mainloop()

if __name__ == "__main__":
    Main()
