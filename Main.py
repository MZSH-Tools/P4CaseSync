# -*- coding: utf-8 -*-

import os
import sys
import threading
import tkinter as Tk
from tkinter import messagebox, ttk

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

def _choose_theme():
    """优先使用带“✔”对勾的原生 Windows 主题，其次退回 clam。"""
    st = ttk.Style()
    names = set(st.theme_names())
    for cand in ("vista", "xpnative", "winnative", "clam"):
        if cand in names:
            try:
                st.theme_use(cand)
                return cand
            except Exception:
                continue
    return st.theme_use()

def Main():
    ctx = {"P4": None}

    root = Tk.Tk()
    root.title("P4 SubmitList Tool")

    # —— 选择主题：尽量让 ttk.Checkbutton 显示“✔”而不是“X”
    _choose_theme()

    # === 窗口居中 ===
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"+{x}+{y}")
    # === 居中结束 ===

    current = {"frame": None}
    state = {"current_cl": "default"}  # 记录当前选择的 changelist

    def ui(fn, *a, **kw):
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
        on_refresh("default")

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
        state["current_cl"] = (changelist or "default")
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
            msg_lines = [f"成功 {ok_count}，失败 {fail_count}，跳过 {skip_count}"]
            tail = logs[-20:]
            if tail:
                msg_lines.append("")
                msg_lines.append("\n".join(tail))
            messagebox.showinfo("执行结果", "\n".join(msg_lines))

        open_progress(total, stop_event=stop_evt, on_closed=after_progress_closed)

        # —— 一致性检测工具（基于当前 CL）
        def _opened_paths_in_current_cl():
            ok2, p2, _t2, _ = GetOpenedPairs(ctx["P4"], state["current_cl"])
            if not ok2:
                return []
            return [src for (src, _dstcand) in p2]

        def _is_exact_match(dst: str) -> bool:
            return any(p == dst for p in _opened_paths_in_current_cl())

        def _find_casefold_match(dst: str):
            dlow = (dst or "").casefold()
            for p in _opened_paths_in_current_cl():
                if p.casefold() == dlow:
                    return p
            return None

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

                    # 方法1
                    if TrySingleMove(ctx["P4"], src, dst):
                        if _is_exact_match(dst):
                            ok_count += 1
                            logs.append(f"[OK] move {src} -> {dst}")
                            ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                            continue
                        # 方法2修正
                        cur = _find_casefold_match(dst)
                        if cur and TryTwoMoves(ctx["P4"], cur, dst) and _is_exact_match(dst):
                            ok_count += 1
                            logs.append(f"[OK] move*2(fix-after-1st) {cur} -> {dst}")
                            ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                            continue
                        else:
                            fail_count += 1
                            logs.append(f"[FAIL] move(after-1st) {src} -> {dst}")
                            ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                            continue

                    # 方法2（直接）
                    cur = _find_casefold_match(dst) or src
                    if TryTwoMoves(ctx["P4"], cur, dst) and _is_exact_match(dst):
                        ok_count += 1
                        logs.append(f"[OK] move*2 {cur} -> {dst}")
                    else:
                        fail_count += 1
                        logs.append(f"[FAIL] move {cur} -> {dst}")

                    ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)

                except Exception as e:
                    fail_count += 1
                    logs.append(f"[EXCEPT] idx={idx} err={e!r}")
                    ui(update_progress, i, ok_count, fail_count, skip_count, f"异常：{e!r}")

            ui(mark_progress_done, ok_count, fail_count, skip_count)

        threading.Thread(target=worker, daemon=True).start()

    show_login()
    root.mainloop()

if __name__ == "__main__":
    Main()
