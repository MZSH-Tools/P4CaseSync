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
    current_theme = _choose_theme()

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
    # 记录当前选中的 changelist（用于一致性检测过滤 opened）
    state = {"current_cl": "default"}

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
        # 记录当前 cl，用于后续一致性检测
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
            # 进度窗关闭后再弹结果（避免与模态冲突）
            msg_lines = [f"成功 {ok_count}，失败 {fail_count}，跳过 {skip_count}"]
            tail = logs[-20:]
            if tail:
                msg_lines.append("")
                msg_lines.append("\n".join(tail))
            messagebox.showinfo("执行结果", "\n".join(msg_lines))

        # 打开进度窗（主线程）
        open_progress(total, stop_event=stop_evt, on_closed=after_progress_closed)

        # === 一致性检测工具 ===
        def _opened_paths_in_current_cl():
            """返回当前 CL 下的已打开 depot 路径列表"""
            ok2, p2, _t2, _ = GetOpenedPairs(ctx["P4"], state["current_cl"])
            if not ok2:
                return []
            return [src for (src, _dstcand) in p2]

        def _is_exact_match(dst: str) -> bool:
            """是否已存在与 dst 完全一致（大小写也一致）的 opened 路径"""
            return any(p == dst for p in _opened_paths_in_current_cl())

        def _find_casefold_match(dst: str):
            """
            在当前 CL 的 opened 中，找到与 dst 大小写不敏感相等的“实际路径”，
            用于在方法1后定位真实源（若大小写仍不符，需要从实际路径做方法2）。
            """
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
                    src = pairs[idx][0]   # 原始 depot 路径
                    dst = targets[idx]    # 期望目标路径（大小写已规范化）
                    if not dst or src == dst:
                        skip_count += 1
                        ui(update_progress, i, ok_count, fail_count, skip_count, "跳过无变化")
                        continue

                    step_msg = f"{src} → {dst}"

                    # ---------- 方法1：单步移动 ----------
                    if TrySingleMove(ctx["P4"], src, dst):
                        # 执行后立刻做一致性检测（必须完全相等）
                        if _is_exact_match(dst):
                            ok_count += 1
                            logs.append(f"[OK] move {src} -> {dst}")
                            ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                            continue
                        else:
                            # 方法1执行了，但大小写等细节不一致，需要通过方法2再修正
                            current_path = _find_casefold_match(dst)
                            if not current_path:
                                # 找不到当前实际项，无法继续纠正
                                fail_count += 1
                                logs.append(f"[FAIL] move(after-1st-move not matched & not found) {src} -> {dst}")
                                ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                                continue
                            # 用实际路径执行方法2
                            if TryTwoMoves(ctx["P4"], current_path, dst) and _is_exact_match(dst):
                                ok_count += 1
                                logs.append(f"[OK] move*2(fix-after-1st) {current_path} -> {dst}")
                                ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                                continue
                            else:
                                fail_count += 1
                                logs.append(f"[FAIL] move*2(fix-after-1st) {current_path} -> {dst}")
                                ui(update_progress, i, ok_count, fail_count, skip_count, step_msg)
                                continue

                    # ---------- 方法2：双步移动（直接尝试） ----------
                    current_path = _find_casefold_match(dst) or src
                    if TryTwoMoves(ctx["P4"], current_path, dst) and _is_exact_match(dst):
                        ok_count += 1
                        logs.append(f"[OK] move*2 {current_path} -> {dst}")
                    else:
                        fail_count += 1
                        logs.append(f"[FAIL] move {current_path} -> {dst}")

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
