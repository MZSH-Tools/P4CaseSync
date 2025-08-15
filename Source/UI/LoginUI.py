# LoginUI.py
# -*- coding: utf-8 -*-

import tkinter as Tk
from tkinter import ttk, messagebox, simpledialog

class LoginFrame(ttk.Frame):
    """
    登录/连接界面（单列 + “连接”按钮）。
    - SetOnConnected(handler): handler(Server, User, Client, PasswordOrNone)
    - SetPrefillGetter(getter): getter() -> (Server, User, Client)，自动回填空白项
    - PromptPassword(): 外部需要密码时调用
    """
    def __init__(self, master, OnConnected=None):
        super().__init__(master, padding=12)
        self.OnConnected = OnConnected
        self._PrefillGetter = None

        g = ttk.LabelFrame(self, text="Perforce")
        g.pack(fill="x", expand=False, pady=(0,8))

        self.ServerVar = Tk.StringVar()
        self.UserVar   = Tk.StringVar()
        self.ClientVar = Tk.StringVar()

        # 行：Server
        row = ttk.Frame(g); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Server (P4PORT):", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.ServerVar).pack(side="left", fill="x", expand=True)

        # 行：User
        row = ttk.Frame(g); row.pack(fill="x", pady=4)
        ttk.Label(row, text="User (P4USER):", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.UserVar).pack(side="left", fill="x", expand=True)

        # 行：Workspace
        row = ttk.Frame(g); row.pack(fill="x", pady=4)
        ttk.Label(row, text="Workspace (P4CLIENT):", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.ClientVar).pack(side="left", fill="x", expand=True)

        ttk.Button(self, text="连接", command=self._on_connect_clicked).pack(anchor="e", pady=(4,0))

    # ------- 回调绑定 -------
    def SetOnConnected(self, handler):
        self.OnConnected = handler

    def SetPrefillGetter(self, getter):
        """getter: callable() -> (Server, User, Client)"""
        self._PrefillGetter = getter
        self.PrefillNow()

    # ------- 动作 -------
    def PrefillNow(self):
        g = self._PrefillGetter
        if not callable(g):
            return
        try:
            s,u,c = g() or ("","","")
        except Exception:
            s=u=c=""
        if not self.ServerVar.get().strip() and s:
            self.ServerVar.set(s)
        if not self.UserVar.get().strip() and u:
            self.UserVar.set(u)
        if not self.ClientVar.get().strip() and c:
            self.ClientVar.set(c)

    def _on_connect_clicked(self):
        server = self.ServerVar.get().strip()
        user   = self.UserVar.get().strip()
        client = self.ClientVar.get().strip()
        if not server or not user or not client:
            messagebox.showwarning("提示", "请填写 Server / User / Workspace")
            return
        if not callable(self.OnConnected):
            messagebox.showerror("错误", "未绑定 OnConnected 回调。")
            return
        self.OnConnected(server, user, client, None)

    # ------- 外部弹出密码 -------
    def PromptPassword(self, title="需要密码", prompt="请输入密码："):
        return simpledialog.askstring(title, prompt, show="*")
