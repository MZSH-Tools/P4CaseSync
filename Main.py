# Main.py
# -*- coding: utf-8 -*-

import os
import sys
import tkinter as Tk
from tkinter import messagebox

def InjectSysPath():
    base = os.path.dirname(os.path.abspath(__file__))
    for p in [base, os.path.join(base, "Source", "UI"), os.path.join(base, "Source", "Logic")]:
        if p not in sys.path:
            sys.path.insert(0, p)
InjectSysPath()

from LoginUI import LoginFrame
from MainUI import MainFrame
from Core import (
    P4Context, GetOpenedPairs, NormalizeName,
    TrySingleMove, TryTwoMoves,
    GetCachedP4User, SaveCachedP4User,
    GetPendingChangelists,   # << 新增导入
)

def NeedsPassword(msg: str) -> bool:
    s = (msg or "").lower()
    keys = ["password", "login", "logged out", "not yet logged in", "p4 login is required", "ticket", "perforce password"]
    return any(k in s for k in keys)

def Main():
    ctx = {"P4": None}

    root = Tk.Tk()
    root.title("P4 SubmitList Tool")
    current = {"frame": None}

    def clear_frame():
        f = current["frame"]
        if f is not None:
            f.destroy()
        current["frame"] = None

    def show_login():
        clear_frame()
        f = LoginFrame(root)
        current["frame"] = f
        f.pack(fill="both", expand=True)
        f.SetOnConnected(on_connected)
        f.SetPrefillGetter(lambda: GetCachedP4User())

    def show_main():
        clear_frame()
        f = MainFrame(root)
        current["frame"] = f
        f.pack(fill="both", expand=True)
        f.SetOnListChangelists(on_list_changelists)  # << 提供下拉获取列表
        f.SetOnRefresh(on_refresh)                   # << 选择后自动刷新
        f.SetOnApply(on_apply)
        # 默认载入 default（给出一个即时视图）
        on_refresh("default")

    # ---- UI 更新便捷函数 ----
    def render_pairs(pairs, targets):
        f = current["frame"]
        if isinstance(f, MainFrame):
            f.RenderPairs(pairs, targets)

    def show_result(ok_count, fail_count, logs_tail):
        f = current["frame"]
        if isinstance(f, MainFrame):
            f.ShowResult(ok_count, fail_count, logs_tail)

    def show_error(msg):
        messagebox.showerror("错误", msg)

    # ---- 事件回调 ----
    def on_connected(server: str, user: str, client: str, password_or_none):
        p4 = P4Context(server, user, client)
        ok, msg = p4.Test()
        if not ok:
            pw = password_or_none
            if NeedsPassword(msg):
                lf = current["frame"]
                pw = lf.PromptPassword() if hasattr(lf, "PromptPassword") else None
            if pw:
                ok, msg = p4.Login(pw)
            if not ok:
                show_error(msg or "登录失败")
                return
        try:
            SaveCachedP4User(server, user, client)
        except Exception:
            pass
        ctx["P4"] = p4
        show_main()

    def on_list_changelists():
        """提供给 MainUI：返回 [(id, label)]，每次展开下拉都会调用"""
        if not ctx["P4"]:
            return [("default", "default (未提交)")]
        return GetPendingChangelists(ctx["P4"], Max=50)

    def on_refresh(changelist: str):
        if not ctx["P4"]:
            show_error("尚未连接 P4。")
            return
        ok, pairs, targets, msg = GetOpenedPairs(ctx["P4"], changelist)
        if not ok:
            show_error(msg or "获取 Opened 列表失败")
            return
        render_pairs(pairs, targets)

    def on_apply(indices, pairs, targets):
        if not ctx["P4"]:
            show_error("尚未连接 P4。")
            return
        ok_count = 0
        fail_count = 0
        logs = []
        for idx in indices:
            try:
                src = pairs[idx][0]
                dst = targets[idx]
                if not dst or src == dst:
                    continue
                if TrySingleMove(ctx["P4"], src, dst):
                    ok_count += 1
                    logs.append(f"[OK] move {src} -> {dst}")
                    continue
                if TryTwoMoves(ctx["P4"], src, dst):
                    ok_count += 1
                    logs.append(f"[OK] move*2 {src} -> {dst}")
                else:
                    fail_count += 1
                    logs.append(f"[FAIL] move {src} -> {dst}")
            except Exception as e:
                fail_count += 1
                logs.append(f"[EXCEPT] idx={idx} err={e!r}")
        show_result(ok_count, fail_count, logs[-50:])

    show_login()
    root.mainloop()

if __name__ == "__main__":
    Main()
