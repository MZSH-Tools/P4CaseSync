# Source/UI/AppUI.py
# -*- coding: utf-8 -*-

import os
import json
import tkinter as Tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import subprocess
from typing import List, Tuple

# 逻辑层
from Source.Logic.Core import (
    P4Context,
    GetOpenedPairs,      # [(DepotPath, LocalPath)]
    TrySingleMove,
    TwoStepMove,
    DepotBaseName,
    LocalBaseName,
    NormalizeChangelist,
)

# ================== 缓存与默认值 ==================

def GetCachePath():
    return str(Path.home() / ".P4CaseSync_UI.json")

def LoadCache():
    try:
        with open(GetCachePath(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def SaveCache(data: dict):
    try:
        with open(GetCachePath(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def GetDefaultsFromP4Set():
    """
    解析 `p4 set`，兜底读环境变量。
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

    result["Server"] = result["Server"] or os.environ.get("P4PORT", "")
    result["User"]   = result["User"]   or os.environ.get("P4USER", "")
    result["Client"] = result["Client"] or os.environ.get("P4CLIENT", "")
    return result

# ================== 主界面（连接） ==================

class AppUI(Tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("P4CaseSync - 连接")
        self.geometry("520x210")
        self.resizable(False, False)

        cache = LoadCache()
        defaults = GetDefaultsFromP4Set()

        self.ServerVar = Tk.StringVar(value=cache.get("Server") or defaults.get("Server") or "")
        self.UserVar   = Tk.StringVar(value=cache.get("User")   or defaults.get("User")   or "")
        self.ClientVar = Tk.StringVar(value=cache.get("Client") or defaults.get("Client") or "")

        self.BuildLayout()

    def BuildLayout(self):
        Pad = {"padx": 8, "pady": 10}
        row = 0

        ttk.Label(self, text="Server").grid(row=row, column=0, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.ServerVar, width=36).grid(row=row, column=1, columnspan=2, sticky="we", **Pad)

        row += 1
        ttk.Label(self, text="User").grid(row=row, column=0, sticky="e", **Pad)
        ttk.Entry(self, textvariable=self.UserVar, width=18).grid(row=row, column=1, sticky="we", **Pad)

        ttk.Label(self, text="Workspace").grid(row=row, column=2, sticky="w", **Pad)
        ttk.Entry(self, textvariable=self.ClientVar, width=18).grid(row=row, column=3, sticky="we", **Pad)

        row += 1
        ttk.Button(self, text="连接", command=self.OnConnect).grid(row=row, column=1, **Pad)
        ttk.Button(self, text="退出", command=self.destroy).grid(row=row, column=2, **Pad)

        for i in range(4):
            self.grid_columnconfigure(i, weight=1)

    def OnConnect(self):
        server = self.ServerVar.get().strip()
        user   = self.UserVar.get().strip()
        client = self.ClientVar.get().strip()

        if not server or not user or not client:
            messagebox.showerror("Error", "Server / User / Workspace 不能为空。")
            return

        SaveCache({"Server": server, "User": user, "Client": client})
        ctx = P4Context(Server=server, User=user, Client=client, Password="")

        # 先试连
        ok, msg = ctx.TestConnection()
        if not ok:
            # 需要登录？尝试弹出密码
            pwd = simpledialog.askstring("需要登录", "请输入密码（不会保存）：", show="*", parent=self)
            if not pwd:
                messagebox.showerror("连接失败", "未提供密码或登录失败。")
                return
            ctx.Password = pwd
            if not ctx.LoginIfNeeded():
                messagebox.showerror("连接失败", "登录失败，请检查账号/密码/权限。")
                return
            ok2, msg2 = ctx.TestConnection()
            if not ok2:
                messagebox.showerror("连接失败", f"连接仍失败：\n{msg2}")
                return

        # 成功：进入检测窗口
        DetectWindow(self, ctx)

# ================== 工具函数 ==================

def ListPendingChangelists(ctx: P4Context) -> List[str]:
    """
    列出当前用户在当前工作区的 pending changelists 编号列表（含 'default' 选项）。
    """
    items = ["default"]
    # p4 changes -s pending -c <client> -u <user>
    r = ctx.Exec(["changes", "-s", "pending", "-c", ctx.Client, "-u", ctx.User])
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            # 形如：Change 12345 on 2025/08/15 by user@client 'desc'
            parts = line.split()
            if len(parts) >= 2 and parts[0].lower() == "change":
                cl = parts[1]
                if cl.isdigit():
                    items.append(cl)
    return items

# ================== 检测窗口 ==================

class DetectWindow(Tk.Toplevel):
    def __init__(self, Master, Ctx: P4Context):
        super().__init__(Master)
        self.title("P4CaseSync - 检测与修改")
        self.geometry("1050x560")
        self.resizable(True, True)

        self.Ctx = Ctx
        self.AllItems: List[Tuple[str,str,str,str,str]] = []  # (depot, local, depot_name, local_name, target_path)
        self.FilterOnlyMismatch = Tk.BooleanVar(value=True)

        self.BuildLayout()
        self.LoadChangelistsAndRefresh()

    def BuildLayout(self):
        Pad = {"padx": 8, "pady": 6}

        # 顶栏：Changelist 下拉 + 开关 + 操作
        top = ttk.Frame(self)
        top.pack(side="top", fill="x")

        ttk.Label(top, text="Changelist: ").pack(side="left", **Pad)
        self.ClVar = Tk.StringVar(value="default")
        self.ClCombo = ttk.Combobox(top, textvariable=self.ClVar, state="readonly", width=18)
        self.ClCombo.pack(side="left", **Pad)
        self.ClCombo.bind("<<ComboboxSelected>>", self.OnChangelistChanged)

        ttk.Checkbutton(top, text="仅显示需要修改的文件", variable=self.FilterOnlyMismatch,
                        command=self.RefreshViews).pack(side="left", **Pad)

        ttk.Button(top, text="应用修改（选中）", command=self.ApplySelected).pack(side="right", **Pad)
        ttk.Button(top, text="应用修改（全部）", command=self.ApplyAll).pack(side="right", **Pad)

        # 中间：左右列表
        mid = ttk.Frame(self)
        mid.pack(side="top", fill="both", expand=True, padx=8, pady=4)

        leftFrame = ttk.LabelFrame(mid, text="原始（Depot → Local）")
        leftFrame.pack(side="left", fill="both", expand=True, padx=(0,4))
        self.LeftList = ttk.Treeview(leftFrame, columns=("Depot","Local"), show="headings", selectmode="extended")
        self.LeftList.heading("Depot", text="Depot 文件名")
        self.LeftList.heading("Local", text="本地文件名")
        self.LeftList.column("Depot", width=300, anchor="w")
        self.LeftList.column("Local", width=300, anchor="w")
        self.LeftList.pack(fill="both", expand=True, padx=6, pady=6)

        rightFrame = ttk.LabelFrame(mid, text="修改后的文件名（双击可编辑）")
        rightFrame.pack(side="left", fill="both", expand=True, padx=(4,0))
        self.RightList = ttk.Treeview(rightFrame, columns=("Target",), show="headings", selectmode="extended")
        self.RightList.heading("Target", text="目标文件名（仅文件名部分）")
        self.RightList.column("Target", width=350, anchor="w")
        self.RightList.pack(fill="both", expand=True, padx=6, pady=6)
        self.RightList.bind("<Double-1>", self.OnEditTarget)

        # 底部状态
        self.StatusVar = Tk.StringVar(value="")
        ttk.Label(self, textvariable=self.StatusVar, foreground="#555555").pack(side="bottom", fill="x", padx=8, pady=6)

    def LoadChangelistsAndRefresh(self):
        # 加载 CL 下拉
        clist = ListPendingChangelists(self.Ctx)
        if not clist:
            clist = ["default"]
        self.ClCombo["values"] = clist
        self.ClCombo.set(clist[0])
        # 加载文件列表
        self.LoadData(changelist=clist[0])

    def OnChangelistChanged(self, _evt):
        self.LoadData(changelist=self.ClVar.get())

    def LoadData(self, changelist: str):
        cl = NormalizeChangelist(changelist)
        pairs = GetOpenedPairs(self.Ctx, cl, Log=lambda s: None)
        items = []
        for depot, local in pairs:
            depot_name = DepotBaseName(depot)
            local_name = LocalBaseName(local)
            target_path = os.path.join(os.path.dirname(local), local_name)  # 默认以本地名为目标
            items.append((depot, local, depot_name, local_name, target_path))
        self.AllItems = items
        self.RefreshViews()

    def FilteredItems(self):
        if not self.FilterOnlyMismatch.get():
            return self.AllItems
        return [it for it in self.AllItems if it[2] != it[3]]

    def RefreshViews(self):
        # 清空
        for w in (self.LeftList, self.RightList):
            for iid in w.get_children():
                w.delete(iid)

        shown = self.FilteredItems()
        for idx, (depot, local, depot_name, local_name, target_path) in enumerate(shown):
            iid = str(idx)
            self.LeftList.insert("", "end", iid=iid, values=(depot_name, local_name))
            self.RightList.insert("", "end", iid=iid, values=(os.path.basename(target_path),))

        self.StatusVar.set(f"共 {len(self.AllItems)} 项；当前显示 {len(shown)} 项。")

    def GetShownItemByIid(self, iid: str):
        shown = self.FilteredItems()
        idx = int(iid)
        if idx < 0 or idx >= len(shown):
            return None
        return shown[idx]

    def OnEditTarget(self, _evt):
        iid = self.RightList.focus()
        if not iid:
            return
        item = self.GetShownItemByIid(iid)
        if not item:
            return
        depot, local, depot_name, local_name, target_path = item
        current_target_name = os.path.basename(target_path)

        new_name = simpledialog.askstring(
            "编辑目标文件名",
            f"原始：{depot_name}\n本地：{local_name}\n\n目标文件名：",
            initialvalue=current_target_name,
            parent=self
        )
        if new_name and new_name.strip():
            new_name = new_name.strip()
            shown = self.FilteredItems()
            shown_idx = int(iid)
            original_tuple = shown[shown_idx]
            original_index = self.AllItems.index(original_tuple)

            new_target_path = os.path.join(os.path.dirname(local), new_name)
            self.AllItems[original_index] = (depot, local, depot_name, local_name, new_target_path)
            self.RightList.item(iid, values=(new_name,))

    def ApplyAll(self):
        items = self.FilteredItems()
        self.ApplyItems(items)

    def ApplySelected(self):
        iids = self.RightList.selection()
        if not iids:
            messagebox.showinfo("提示", "请先选择右侧列表的条目。")
            return
        items = []
        for iid in iids:
            it = self.GetShownItemByIid(iid)
            if it:
                items.append(it)
        self.ApplyItems(items)

    def ApplyItems(self, items: List[Tuple[str,str,str,str,str]]):
        if not items:
            messagebox.showinfo("提示", "没有可处理的条目。")
            return

        success = 0
        failed  = 0
        skipped = 0
        msgs = []

        for depot, local, depot_name, local_name, target_path in items:
            if not os.path.exists(local):
                skipped += 1
                msgs.append(f"[Skip] 本地不存在：{local}")
                continue

            target_dir = os.path.dirname(local)
            target_name_only = os.path.basename(target_path)
            final_target = os.path.join(target_dir, target_name_only)

            if depot_name == target_name_only:
                skipped += 1
                msgs.append(f"[Skip] 目标与 depot 名相同：{depot_name}")
                continue

            if TrySingleMove(local, final_target, self.Ctx, Log=lambda s: None):
                success += 1
                msgs.append(f"[OK] {depot_name} -> {target_name_only}")
                continue

            if TwoStepMove(local, final_target, self.Ctx, Log=lambda s: None):
                success += 1
                msgs.append(f"[OK*] {depot_name} -> {target_name_only}（两步）")
            else:
                failed += 1
                msgs.append(f"[Fail] {depot_name} -> {target_name_only}")

        summary = f"完成：成功 {success}，失败 {failed}，跳过 {skipped}"
        messagebox.showinfo("结果", summary + "\n\n" + "\n".join(msgs[:50]) + ("\n..." if len(msgs) > 50 else ""))
