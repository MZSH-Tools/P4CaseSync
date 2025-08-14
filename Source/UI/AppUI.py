# Source/UI/AppUI.py
# -*- coding: utf-8 -*-

import os
import json
import threading
import tkinter as Tk
from tkinter import ttk, messagebox
from pathlib import Path
import subprocess

# 逻辑层
from Source.Logic.Core import (
    P4Context,
    SyncDepotCaseToLocal,
    SubmitChange,
)

# ================== Cache & Defaults ==================

def GetCachePath():
    return str(Path.home() / ".P4CaseSync_UI.json")

def LoadCache():
    try:
        with open(GetCachePath(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def SaveCache(Data: dict):
    try:
        with open(GetCachePath(), "w", encoding="utf-8") as f:
            json.dump(Data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def GetDefaultsFromP4Set():
    """
    解析 `p4 set`（Windows 优先），兜底读环境变量。
    返回 { "Server": "...", "User": "...", "Client": "..." }
    """
    result = {"Server": "", "User": "", "Client": ""}
    try:
        out = subprocess.run(["p4", "set"], capture_output=True, text=True)
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                s = line.strip()
                if s.upper().startswith("P4PORT=") and not result["Server"]:
                    result["Server"] = s.split("=", 1)[1].split(" (")[0].strip()
                elif s.upper().startswith("P4USER=") and not result["User"]:
                    result["User"] = s.split("=", 1)[1].split(" (")[0].strip()
                elif s.upper().startswith("P4CLIENT=") and not result["Client"]:
                    result["Client"] = s.split("=", 1)[1].split(" (")[0].strip()
    except Exception:
        pass

    # 兜底环境变量
    if not result["Server"]:
        result["Server"] = os.environ.get("P4PORT", "")
    if not result["User"]:
        result["User"] = os.environ.get("P4USER", "")
    if not result["Client"]:
        result["Client"] = os.environ.get("P4CLIENT", "")
    return result

# ================== UI ==================

class AppUI(Tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("P4CaseSync - Match Depot Case To Local")
        self.geometry("740x520")
        self.resizable(False, False)

        cache = LoadCache()
        defaults = GetDefaultsFromP4Set()

        # 受控变量
        self.ServerVar = Tk.StringVar(value=cache.get("Server") or defaults.get("Server") or "")
        self.UserVar   = Tk.StringVar(value=cache.get("User")   or defaults.get("User")   or "")
        self.ClientVar = Tk.StringVar(value=cache.get("Client") or defaults.get("Client") or "")
        self.PassVar   = Tk.StringVar(value="")
        self.ChangeVar = Tk.StringVar(value="default")  # 不缓存
        self.DescVar   = Tk.StringVar(value="")
        self.DryRunVar = Tk.BooleanVar(value=False)
        self.AutoSubmitVar = Tk.BooleanVar(value=False)

        self.BuildLayout()

    # ---------- Layout ----------

    def BuildLayout(self):
        Pad = {"padx": 8, "pady": 6}
        row = 0

        # 行 1：Server
        ttk.Label(self, text="Server").grid(row=row, column=0, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.ServerVar, width=50).grid(row=row, column=1, columnspan=3, sticky="we", **Pad)

        # 行 2：User / Workspace
        row += 1
        ttk.Label(self, text="User").grid(row=row, column=0, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.UserVar, width=24).grid(row=row, column=1, sticky="we", **Pad)

        ttk.Label(self, text="Workspace").grid(row=row, column=2, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.ClientVar, width=24).grid(row=row, column=3, sticky="we", **Pad)

        # 行 3：Password / Changelist
        row += 1
        ttk.Label(self, text="Password (optional)").grid(row=row, column=0, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.PassVar, show="*", width=24).grid(row=row, column=1, sticky="we", **Pad)

        ttk.Label(self, text="Changelist").grid(row=row, column=2, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.ChangeVar, width=24).grid(row=row, column=3, sticky="we", **Pad)

        # 行 4：提交描述
        row += 1
        ttk.Label(self, text="Submit Description").grid(row=row, column=0, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.DescVar, width=60).grid(row=row, column=1, columnspan=3, sticky="we", **Pad)

        # 行 5：选项
        row += 1
        ttk.Checkbutton(self, text="Dry Run (no changes)", variable=self.DryRunVar).grid(row=row, column=1, sticky="w", **Pad)
        ttk.Checkbutton(self, text="Auto Submit", variable=self.AutoSubmitVar).grid(row=row, column=2, sticky="w", **Pad)

        # 行 6：进度条
        row += 1
        self.Progress = ttk.Progressbar(self, orient="horizontal", mode="determinate", length=560)
        self.Progress.grid(row=row, column=0, columnspan=4, sticky="we", padx=8, pady=(14, 4))

        # 行 7：按钮
        row += 1
        ttk.Button(self, text="运行", command=self.OnRun).grid(row=row, column=1, **Pad)
        ttk.Button(self, text="退出", command=self.destroy).grid(row=row, column=2, **Pad)

        # 行 8：日志
        row += 1
        self.LogText = Tk.Text(self, height=14)
        self.LogText.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=8, pady=8)

        for i in range(4):
            self.grid_columnconfigure(i, weight=1)

    # ---------- Helpers ----------

    def AppendLog(self, Text: str):
        msg = Text if Text.endswith("\n") else (Text + "\n")
        self.LogText.insert("end", msg)
        self.LogText.see("end")
        self.update_idletasks()

    def SetTotal(self, Total: int):
        self.Progress["maximum"] = max(1, Total)
        self.Progress["value"] = 0
        self.update_idletasks()

    def StepProgress(self, Done: int):
        self.Progress["value"] = min(self.Progress["maximum"], Done)
        self.update_idletasks()

    # ---------- Actions ----------

    def OnRun(self):
        server = self.ServerVar.get().strip()
        user   = self.UserVar.get().strip()
        client = self.ClientVar.get().strip()
        password = self.PassVar.get()
        change = (self.ChangeVar.get().strip() or "default")
        desc   = self.DescVar.get().strip()
        dryrun = self.DryRunVar.get()
        autosubmit = self.AutoSubmitVar.get()

        # 校验必要字段
        if not server or not user or not client:
            messagebox.showerror("Error", "Server / User / Workspace 不能为空。")
            return

        # 写缓存（不含密码与 Changelist）
        SaveCache({"Server": server, "User": user, "Client": client})

        ctx = P4Context(Server=server, User=user, Client=client, Password=password)

        def Worker():
            # 登录（可选）
            self.AppendLog(f"Testing connection: {server} ({user}/{client}) ...")
            if password:
                if not ctx.LoginIfNeeded():
                    self.AppendLog("[Error] Login failed.")
                    messagebox.showerror("Login Failed", "登录失败，请检查密码或权限。")
                    return

            ok, msg = ctx.TestConnection()
            if not ok:
                self.AppendLog(msg)
                messagebox.showerror("Connection Failed", "连接失败，请检查 Server/User/Workspace。")
                return
            self.AppendLog("Connection OK.")

            # 执行同步
            progress = {"SetTotal": self.SetTotal, "Step": self.StepProgress}
            changed = SyncDepotCaseToLocal(ctx, change, dryrun, self.AppendLog, Progress=progress)
            self.AppendLog(f"Files fixed: {changed}")

            # 可选自动提交
            if autosubmit and not dryrun:
                if SubmitChange(ctx, change, desc, self.AppendLog):
                    self.AppendLog("Submit completed.")
                else:
                    self.AppendLog("[Error] Submit failed.")

        threading.Thread(target=Worker, daemon=True).start()
