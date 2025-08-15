# Main.py
# -*- coding: utf-8 -*-

import os
import sys
import tkinter as Tk
from tkinter import messagebox

# 若你使用 Source/ 目录结构，打开下一行注入；否则可忽略
def InjectSysPath():
    base = os.path.dirname(os.path.abspath(__file__))
    for p in [
        base,
        os.path.join(base, "Source", "UI"),
        os.path.join(base, "Source", "Logic"),
    ]:
        if p not in sys.path:
            sys.path.insert(0, p)
InjectSysPath()

from LoginUI import LoginFrame
from MainUI import MainFrame
from Core import (
    P4Context, GetOpenedPairs, NormalizeName,
    TrySingleMove, TryTwoMoves,
    GetCachedP4User, SaveCachedP4User,
)

def NeedsPassword(msg: str) -> bool:
    s = (msg or "").lower()
    keys = [
        "password", "login", "logged out", "not yet logged in",
        "p4 login is required", "ticket", "perforce password"
    ]
    return any(k in s for k in keys)

def Main():
    # ---- 全局上下文（Main 负责调度）----
    ctx = {"P4": None}

    # ---- Tk 根窗口与当前 Frame 引用 ----
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
        f.SetOnConnected(on_connected)  # 绑定连接回调
        # 绑定预填（仅覆盖空白）
        f.SetPrefillGetter(lambda: GetCachedP4User())

    def show_main():
        clear_frame()
        f = MainFrame(root)
        current["frame"] = f
        f.pack(fill="both", expand=True)
        f.SetOnRefresh(on_refresh)
        f.SetOnApply(on_apply)

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

    # ---- 事件回调（Main 连接 UI 与 Logic）----
    def on_connected(server: str, user: str, client: str, password_or_none):
        # 1) 构建 P4 上下文并测试
        p4 = P4Context(server, user, client)
        ok, msg = p4.Test()
        if not ok:
            # 可能需要密码：若未提供或失败，弹出一次
            pw = password_or_none
            if NeedsPassword(msg):
                lf = current["frame"]
                pw = lf.PromptPassword() if hasattr(lf, "PromptPassword") else None
            if pw:
                ok, msg = p4.Login(pw)
            if not ok:
                show_error(msg or "登录失败")
                return

        # 2) 写回缓存
        try:
            SaveCachedP4User(server, user, client)
        except Exception:
            pass

        # 3) 切换到主界面
        ctx["P4"] = p4
        show_main()

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
        # indices：用户勾选的需要应用的行
        for idx in indices:
            try:
                src = pairs[idx][0]
                dst = targets[idx]
                if not dst or src == dst:
                    continue
                # 单步尝试
                if TrySingleMove(ctx["P4"], src, dst):
                    ok_count += 1
                    logs.append(f"[OK] move {src} -> {dst}")
                    continue
                # 双步（大小写敏感修正）
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

    # 初始显示登录页并进入事件循环
    show_login()
    root.mainloop()

if __name__ == "__main__":
    Main()
