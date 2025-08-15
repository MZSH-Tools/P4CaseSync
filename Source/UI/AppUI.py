# AppUI.py
# -*- coding: utf-8 -*-

import tkinter as Tk
from tkinter import messagebox
from LoginUI import LoginFrame
from MainUI import MainFrame

class AppUI(Tk.Tk):
    """
    主窗口：只负责界面切换与把 UI 事件转交给 Main。
    - BindHandlers(OnConnected, OnRefresh, OnApply) 由 Main 调用，用于注册业务回调
    - SwitchToMain() 切换到运行界面（由 Main 在连接成功后调用）
    - RenderPairs(pairs, targets) / ShowResult(...) / ShowError(...) 供 Main 回填数据与结果
    """
    def __init__(self):
        super().__init__()
        self.title("P4 提交列表修改器")
        self.geometry("760x520")
        self.Minsize(680, 420)

        self.CurrentFrame = None
        self.Handlers = {
            "OnConnected": None,   # def OnConnected(Server, User, Client, PasswordOrNone) -> None
            "OnRefresh":   None,   # def OnRefresh(Changelist) -> None
            "OnApply":     None,   # def OnApply(Indices, Pairs, Targets) -> None
        }

        # 初始显示登录界面
        self.ShowLogin()

    # ------- 外部 API（供 Main 调用） -------
    def BindHandlers(self, **kwargs):
        # 支持：OnConnected, OnRefresh, OnApply
        for k, v in kwargs.items():
            if k in self.Handlers:
                self.Handlers[k] = v

        # 把回调下发给子 Frame（如果存在）
        if isinstance(self.CurrentFrame, LoginFrame) and self.Handlers["OnConnected"]:
            self.CurrentFrame.SetOnConnected(self.Handlers["OnConnected"])

        if isinstance(self.CurrentFrame, MainFrame):
            if self.Handlers["OnRefresh"]:
                self.CurrentFrame.SetOnRefresh(self.Handlers["OnRefresh"])
            if self.Handlers["OnApply"]:
                self.CurrentFrame.SetOnApply(self.Handlers["OnApply"])

    def SwitchToMain(self):
        self.ClearFrame()
        self.CurrentFrame = MainFrame(self)
        self.CurrentFrame.pack(fill="both", expand=True)

        # 将回调注入到主界面
        if self.Handlers["OnRefresh"]:
            self.CurrentFrame.SetOnRefresh(self.Handlers["OnRefresh"])
        if self.Handlers["OnApply"]:
            self.CurrentFrame.SetOnApply(self.Handlers["OnApply"])

    def RenderPairs(self, Pairs, Targets):
        """Main 把计算好的 (Pairs, Targets) 回填到 UI。"""
        if isinstance(self.CurrentFrame, MainFrame):
            self.CurrentFrame.RenderPairs(Pairs, Targets)

    def ShowResult(self, OkCount, FailCount, LogsTail):
        if isinstance(self.CurrentFrame, MainFrame):
            self.CurrentFrame.ShowResult(OkCount, FailCount, LogsTail)
        else:
            messagebox.showinfo("结果", f"成功：{OkCount} 失败：{FailCount}")

    def ShowError(self, Msg):
        messagebox.showerror("错误", Msg)

    # ------- 内部：窗口管理 -------
    def Minsize(self, W, H):
        try:
            self.minsize(W, H)
        except Exception:
            pass

    def ClearFrame(self):
        if self.CurrentFrame is not None:
            self.CurrentFrame.destroy()
            self.CurrentFrame = None

    def ShowLogin(self):
        self.ClearFrame()
        self.CurrentFrame = LoginFrame(self)
        self.CurrentFrame.pack(fill="both", expand=True)

        # 如果 Main 已经绑定过 OnConnected，则立即注入
        if self.Handlers["OnConnected"]:
            self.CurrentFrame.SetOnConnected(self.Handlers["OnConnected"])
