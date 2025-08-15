# LoginUI.py
# -*- coding: utf-8 -*-

import os
import tkinter as Tk
from tkinter import ttk, messagebox, simpledialog

class LoginFrame(ttk.Frame):
    """
    登录/连接界面（单列布局 + 一个“连接”按钮）。
    - SetOnConnected(handler): 由 AppUI/Main 绑定。handler(Server, User, Client, PasswordOrNone)
    - PromptPassword(): 提供给外层在需要时调用以弹出密码窗口
    UI 只收集输入并把数据交给 Main；是否需要密码、如何登录由 Main 决策。
    """
    def __init__(self, Master, OnConnected=None):
        super().__init__(Master, padding=12)
        self.OnConnected = OnConnected

        # 输入项
        self.ServerVar = Tk.StringVar()
        self.UserVar   = Tk.StringVar(value=os.environ.get("P4USER", ""))
        self.ClientVar = Tk.StringVar(value=os.environ.get("P4CLIENT", ""))

        Row = 0
        ttk.Label(self, text="Server:").grid(row=Row, column=0, sticky="w", pady=(0,6))
        ttk.Entry(self, textvariable=self.ServerVar, width=40).grid(row=Row, column=1, sticky="ew", pady=(0,6)); Row += 1

        ttk.Label(self, text="User:").grid(row=Row, column=0, sticky="w", pady=(0,6))
        ttk.Entry(self, textvariable=self.UserVar, width=40).grid(row=Row, column=1, sticky="ew", pady=(0,6)); Row += 1

        ttk.Label(self, text="Workspace:").grid(row=Row, column=0, sticky="w", pady=(0,12))
        ttk.Entry(self, textvariable=self.ClientVar, width=40).grid(row=Row, column=1, sticky="ew", pady=(0,12)); Row += 1

        ttk.Button(self, text="连接", command=self.OnConnectClicked).grid(row=Row, column=0, columnspan=2, sticky="ew")
        self.columnconfigure(1, weight=1)

    # ------- 外部绑定 -------
    def SetOnConnected(self, Handler):
        self.OnConnected = Handler

    # ------- 事件 -------
    def OnConnectClicked(self):
        Server = self.ServerVar.get().strip()
        User   = self.UserVar.get().strip()
        Client = self.ClientVar.get().strip()
        if not Server or not User or not Client:
            messagebox.showwarning("提示", "请填写 Server / User / Workspace")
            return

        if self.OnConnected is None:
            messagebox.showerror("错误", "未绑定 OnConnected 回调。")
            return

        # 不在 UI 内部直接登录；把输入交给 Main，由 Main 决定是否需要密码与登录流程
        self.OnConnected(Server, User, Client, None)

    # ------- 提供给外层调用的密码弹窗 -------
    def PromptPassword(self, Title="需要密码", Prompt="请输入密码："):
        return simpledialog.askstring(Title, Prompt, show="*")
