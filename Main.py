# Main.py
# -*- coding: utf-8 -*-

import os
import sys
import threading
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
    P4Context, GetOpenedPairs,
    TrySingleMove, TryTwoMoves,
    GetCachedP4User, SaveCachedP4User,
    GetPendingChangelists,
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

    def ui(fn, *a, **kw):
        """把 UI 更新投递到主线程"""
        root.after(0, lambda: fn(*a, **kw))

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
        f.SetOnListChangelists(on_list_changelists)
        f.SetOnRefresh(on_refresh)
        f.SetOnApply(on_apply)
        on_refresh("default")  # 默认载入

    # ---- UI 便捷 ----
    def render_pairs(pairs, targets):
        f = current["frame"]
        if isinstance(f, MainFrame):
            f.RenderPairs(pairs, targets)

    def open_progress(total, stop_event, on_closed):
        f = current["frame"]
        if isinstance(f, MainFrame):
            f.OpenProgress(total, stop_event, on_closed)

    def update_progress(done, ok, fail, skip, msg=""):
        f = current["frame"]
        if isinstance(f, MainFrame):
            f.UpdateProgress(done, ok, fail, skip, msg)

    def mark_progress_done(ok, fail, skip):
        f = current["frame"]
        if isinstance(f, MainFrame):
            f.MarkProgressDone(ok, fail, skip)

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
        if not ctx["P4"]:
            return [("default", "default (未提交)")]
        return GetPendingChangelists(ctx["P4"], Max=50)

    def on_refresh(changelist: str):
        if not ctx["P4"]:
            show_error("尚未连接 P4。"); return
        ok, pairs, targets, msg = GetOpenedPairs(ctx["P4"], changelist)
        if not ok:
            show_error(msg or "获取 Opened 列表失败"); return
        render_pairs(pairs, targets)

    def on_apply(indices, pairs, targets):
        if not ctx["P4"]:
            show_error("尚未连接 P4。"); return

        total = len(indices)
        if total == 0:
            messagebox.showinfo("提示", "没有需要应用的项。"); return

        stop_evt = threading.Event()
        logs = []
        ok_count = 0
        fail_count = 0
        skip_count = 0

        def after_progress_closed():
            # 进度窗关闭后再弹结果（避免与模态冲突）
            msg_lines = [f"成功 {ok_count}，失败 {fail_count}，跳过 {skip_count}"]
            tail = logs[-20:]
            if tail:
                msg_lines.append("")
                msg_lines.append("\n".join(tail))
            messagebox.showinfo("执行结果", "\n".join(msg_lines))

        # 打开进度窗（主线程）
        open_progress(total, stop_event=stop_evt, on_closed=after_progress_closed)

        def worker():
            nonlocal ok_count, fail_count, skip_count
            for i, idx in enumerate(indices, start=1):
                if stop_evt.is_set():
                    logs.append("[INTERRUPT] 用户中断")
                    break
                try:
                    src = pairs[idx][0]
                    dst = targets[idx]
                    if not dst or src == dst:
                        skip_count += 1
                        ui(update_progress, i, ok_count, fail_count, skip_count, "跳过无变化")
                        continue

                    step_msg = f"{src} → {dst}"

                    # 单步尝试
                    if TrySingleMove(ctx["P4"], src, dst):
                        ok_count += 1
                        logs.append(f"[OK] move {src} -> {dst}")
                        ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                        continue

                    # 双步
                    if TryTwoMoves(ctx["P4"], src, dst):
                        ok_count += 1
                        logs.append(f"[OK] move*2 {src} -> {dst}")
                    else:
                        fail_count += 1
                        logs.append(f"[FAIL] move {src} -> {dst}")

                    ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)

                except Exception as e:
                    fail_count += 1
                    logs.append(f"[EXCEPT] idx={idx} err={e!r}")
                    ui(update_progress, i, ok_count, fail_count, skip_count, f"异常：{e!r}")

            # 通知 UI：处理完毕（或被中断），按钮变“关闭”，等待用户点击
            ui(mark_progress_done, ok_count, fail_count, skip_count)

        threading.Thread(target=worker, daemon=True).start()

    show_login()
    root.mainloop()

if __name__ == "__main__":
    Main()
