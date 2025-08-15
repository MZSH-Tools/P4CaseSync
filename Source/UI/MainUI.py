# -*- coding: utf-8 -*-

import re
import tkinter as Tk
from tkinter import ttk, messagebox

def _basename(path: str) -> str:
    if not path: return ""
    p = path.replace("\\", "/")
    return p.rsplit("/", 1)[-1]

def _natural_key(s: str):
    # 自然排序：a2 < a10；大小写不敏感
    s = s or ""
    parts = re.split(r'(\d+)', s.casefold())
    return [int(p) if p.isdigit() else p for p in parts]

# ------------------ 进度弹窗 ------------------
class ProgressDialog(Tk.Toplevel):
    def __init__(self, master, total: int, stop_event=None):
        super().__init__(master)
        self.title("执行中…")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._total = max(1, int(total))
        self._completed = False
        self._on_closed = None
        self._stop_event = stop_event  # threading.Event

        pad = 10
        box = ttk.Frame(self, padding=pad); box.pack(fill="both", expand=True)

        self.Bar = ttk.Progressbar(box, orient="horizontal", mode="determinate", maximum=self._total)
        self.Bar.pack(fill="x")

        counts = ttk.Frame(box); counts.pack(fill="x", pady=(pad, 0))
        self.OkVar   = Tk.StringVar(value="成功 0")
        self.FailVar = Tk.StringVar(value="失败 0")
        self.SkipVar = Tk.StringVar(value="跳过 0")
        ttk.Label(counts, textvariable=self.OkVar).pack(side="left")
        ttk.Label(counts, text="  /  ").pack(side="left")
        ttk.Label(counts, textvariable=self.FailVar).pack(side="left")
        ttk.Label(counts, text="  /  ").pack(side="left")
        ttk.Label(counts, textvariable=self.SkipVar).pack(side="left")

        self.StateVar = Tk.StringVar(value=f"执行中… 0/{self._total}")
        ttk.Label(box, textvariable=self.StateVar).pack(anchor="w", pady=(6, 0))

        self.MsgVar = Tk.StringVar(value="")
        ttk.Label(box, textvariable=self.MsgVar, foreground="#444").pack(anchor="w", pady=(2, 0))

        btns = ttk.Frame(box); btns.pack(fill="x", pady=(pad, 0))
        self.ActionBtn = ttk.Button(btns, text="中断", command=self._on_action)
        self.ActionBtn.pack(anchor="center")

        self.protocol("WM_DELETE_WINDOW", self._on_action)

        # 居中到父窗口
        self.update_idletasks()
        try:
            px = master.winfo_rootx(); py = master.winfo_rooty()
            pw = master.winfo_width(); ph = master.winfo_height()
            w = self.winfo_width();    h = self.winfo_height()
            self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")
        except Exception:
            pass

    def SetOnClosed(self, fn):
        self._on_closed = fn

    def Update(self, done: int, ok: int, fail: int, skip: int, msg: str = ""):
        done = max(0, min(int(done), self._total))
        self.Bar["value"] = done
        self.OkVar.set(f"成功 {ok}")
        self.FailVar.set(f"失败 {fail}")
        self.SkipVar.set(f"跳过 {skip}")
        state = "已完成" if self._completed else "执行中…"
        self.StateVar.set(f"{state} {done}/{self._total}")
        self.MsgVar.set(msg or "")
        self.update_idletasks()

    def MarkDone(self, ok: int, fail: int, skip: int):
        self._completed = True
        self.Bar["value"] = self.Bar["maximum"]
        self.ActionBtn.configure(text="关闭")
        self.Update(self._total, ok, fail, skip, "")

    def _on_action(self):
        if not self._completed:
            try:
                if self._stop_event:
                    self._stop_event.set()
            except Exception:
                pass
            self.ActionBtn.configure(state="disabled", text="中断中…")
        else:
            try:
                self.grab_release()
            except Exception:
                pass
            self.destroy()
            try:
                if callable(self._on_closed):
                    self._on_closed()
            except Exception:
                pass

# ------------------ 主界面 ------------------
class MainFrame(ttk.Frame):
    """
    单列列表（两行：更改前/更改后）+ 多选（仅高亮）+ 勾选（批量应用）
    顶部：Changelist 下拉 + 过滤 + 颜色说明 + 操作说明
    颜色规则：
      - 灰：更改前后完全一致
      - 绿：自动修正（与自动一致）
      - 红：手动修改（与自动不一致）
    双击整行可编辑“更改后”。
    """

    # 统一纯色，减少纹理/残影
    HI_BG     = "#e6f2ff"
    NORM_BG   = "#f8f8f8"
    SEP_BG    = "#dddddd"
    CANVAS_BG = "#ffffff"

    # 文本颜色
    COL_GRAY  = "#888888"   # 一致（置灰）
    COL_GREEN = "#2a6f2a"   # 自动修正（绿色）
    COL_RED   = "#cc3333"   # 手动修改（红色）

    def __init__(self, master):
        super().__init__(master, padding=8)
        self.OnListChangelists = None
        self.OnRefresh = None
        self.OnApply   = None

        # 复选框样式
        self._style = ttk.Style()
        self._style.configure("Row.TCheckbutton", background=self.NORM_BG)
        self._style.map("Row.TCheckbutton",
                        background=[("active", self.NORM_BG), ("selected", self.NORM_BG)])
        self._style.configure("Head.TCheckbutton", background=self.CANVAS_BG)
        self._style.map("Head.TCheckbutton",
                        background=[("active", self.CANVAS_BG), ("selected", self.CANVAS_BG)])

        # ===== 顶部：Changelist 下拉 + 过滤 =====
        top = ttk.Frame(self); top.pack(fill="x", pady=(0,8))
        ttk.Label(top, text="Changelist#:").pack(side="left")

        self.CLVar = Tk.StringVar()
        self.CLCombo = ttk.Combobox(
            top, textvariable=self.CLVar, state="readonly", width=48,
            postcommand=self._refresh_changelist_options
        )
        self.CLCombo.pack(side="left", padx=6, fill="x", expand=True)
        self.CLCombo.bind("<<ComboboxSelected>>", self._on_cl_selected)

        self.OnlyChangedVar = Tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="仅显示需要修改的文件",
                        variable=self.OnlyChangedVar,
                        command=self._apply_filter).pack(side="left", padx=(12,0))

        # ===== 列表上方：全选/统计 + 颜色说明 + 操作说明 =====
        header = ttk.Frame(self); header.pack(fill="x", pady=(8,4))
        self.SelectAllVar = Tk.BooleanVar(value=False)
        self.SelectAllChk = ttk.Checkbutton(
            header, text="全选(可见)",
            variable=self.SelectAllVar,
            command=self._on_select_all_toggle,
            style="Head.TCheckbutton"
        )
        self.SelectAllChk.pack(side="left")

        self.CheckedStatVar = Tk.StringVar(value="已勾选 0 / 0")
        self.CheckedStatLbl = ttk.Label(header, textvariable=self.CheckedStatVar)
        self.CheckedStatLbl.pack(side="right")

        # —— 颜色说明行
        legend = ttk.Frame(self); legend.pack(fill="x")
        def chip(parent, color, text):
            box = Tk.Frame(parent, width=10, height=10, bg=color, bd=1, relief="solid")
            box.pack(side="left", padx=(0,6))
            ttk.Label(parent, text=text).pack(side="left", padx=(0,12))
        chip(legend, self.COL_GRAY,  "灰：更改前后完全一致")
        chip(legend, self.COL_GREEN, "绿：自动修正（与自动一致）")
        chip(legend, self.COL_RED,   "红：手动修改（与自动不一致）")

        # —— 操作说明
        hint = ttk.Label(self, text="提示：双击列表行可编辑“更改后”。")
        hint.pack(fill="x", pady=(2,6))

        # ===== 中部：列表（滚动） =====
        mid = ttk.Frame(self); mid.pack(fill="both", expand=True)

        self.Canvas = Tk.Canvas(mid, highlightthickness=0, bg=self.CANVAS_BG)
        vbar = ttk.Scrollbar(mid, orient="vertical", command=self.Canvas.yview)
        self.Canvas.configure(yscrollcommand=vbar.set)
        self.Canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="left", fill="y")

        self.ListArea = Tk.Frame(self.Canvas, bg=self.NORM_BG)
        self._canvas_item = self.Canvas.create_window((0, 0), window=self.ListArea, anchor="nw")
        self.ListArea.bind("<Configure>", lambda e: self.Canvas.configure(scrollregion=self.Canvas.bbox("all")))
        self.Canvas.bind("<Configure>", self._on_canvas_resize)

        # ===== 底部：应用按钮 =====
        btnBox = ttk.Frame(self); btnBox.pack(fill="x", pady=(8,0))
        self.ApplyBtn = ttk.Button(btnBox, text="应用修改", command=self._on_apply)
        self.ApplyBtn.pack(anchor="center")

        # ===== 数据状态 =====
        self._Pairs        = []  # [(src, dstCand), ...]
        self._Targets      = []  # 当前“更改后”（用户可改）
        self._AutoTargets  = []  # 自动修正值（初始化时记录，用于与当前值比对）
        self._Order        = []  # 排序后的全量索引
        self._ViewIdx      = []  # 可见 -> 全量
        self._SelVars      = []  # 与全量对齐的 BooleanVar（勾选）
        self._Rows         = {}  # {full_idx: rowFrame}
        self._ChkRefs      = {}  # {full_idx: ttk.Checkbutton}
        self._SelectedSet  = set()
        self._LastAnchor   = None
        self._BulkChecking = False
        self._ProgDlg      = None

        # 下拉内容
        self._CLItems = []
        self._CLLabelToId = {}
        self._set_cl_items([("default", "default (未提交)")])
        self.CLCombo.set("default (未提交)")

    # ---------- 回调绑定 ----------
    def SetOnListChangelists(self, fn): self.OnListChangelists = fn
    def SetOnRefresh(self, fn):         self.OnRefresh = fn
    def SetOnApply(self, fn):           self.OnApply = fn

    # ---------- 对外：渲染 ----------
    def RenderPairs(self, pairs, targets):
        """
        pairs: [(src_depot, _dstcand_ignored), ...]
        targets: [dst_depot_by_core, ...]  —— 这是“自动修正值（以本地大小写为准）”
        """
        self._Pairs        = list(pairs)
        self._Targets      = list(targets)      # 当前显示值（可编辑）
        self._AutoTargets  = list(targets)      # 记录自动修正值，用于颜色判断

        # 初始化/扩展勾选变量（默认勾选）
        n = len(self._Pairs)
        if len(self._SelVars) < n:
            for _ in range(n - len(self._SelVars)):
                self._SelVars.append(Tk.BooleanVar(value=True))

        # 自动排序：优先更改后文件名，其次更改后完整路径
        keys = []
        for i, (src, _dstcand) in enumerate(self._Pairs):
            dst  = self._Targets[i] if i < len(self._Targets) else ""
            name = _basename(dst) or _basename(src)
            keys.append((_natural_key(name), _natural_key(dst or ""), i))
        keys.sort()
        self._Order = [i for (_k1, _k2, i) in keys]

        self._refresh_view()

    def ShowResult(self, ok_count, fail_count, logs_tail):
        if logs_tail:
            messagebox.showinfo("日志(末尾)", "\n".join(logs_tail[-20:]))

    # ---------- 进度弹窗 API（给 Main 调用） ----------
    def OpenProgress(self, total: int, stop_event, on_closed=None):
        if self._ProgDlg:
            try: self._ProgDlg.destroy()
            except Exception: pass
        self._ProgDlg = ProgressDialog(self.winfo_toplevel(), total, stop_event=stop_event)
        if on_closed:
            self._ProgDlg.SetOnClosed(on_closed)

    def UpdateProgress(self, done: int, ok: int, fail: int, skip: int, msg: str = ""):
        if self._ProgDlg:
            self._ProgDlg.Update(done, ok, fail, skip, msg)

    def MarkProgressDone(self, ok: int, fail: int, skip: int):
        if self._ProgDlg:
            self._ProgDlg.MarkDone(ok, fail, skip)

    # ---------- 下拉 ----------
    def _set_cl_items(self, items):
        self._CLItems = list(items)
        self._CLLabelToId = {label: id_ for (id_, label) in self._CLItems}
        self.CLCombo["values"] = [label for (_id, label) in self._CLItems]

    def _refresh_changelist_options(self):
        if not callable(self.OnListChangelists): return
        try:
            items = self.OnListChangelists() or []
        except Exception:
            items = []
        if not any(i[0] == "default" for i in items):
            items = [("default", "default (未提交)")] + items
        else:
            items = [i for i in items if i[0] == "default"] + [i for i in items if i[0] != "default"]
        self._set_cl_items(items)

    def _on_cl_selected(self, _evt=None):
        if not callable(self.OnRefresh):
            messagebox.showerror("错误", "未绑定 OnRefresh 回调。"); return
        label = self.CLVar.get()
        cl_id = self._CLLabelToId.get(label, "default")
        self.OnRefresh(cl_id)

    # ---------- 视图 ----------
    def _on_canvas_resize(self, evt):
        self.Canvas.itemconfig(self._canvas_item, width=evt.width)

    def _apply_filter(self):
        self._refresh_view()

    # —— 颜色判定
    def _color_for(self, idx):
        src  = self._Pairs[idx][0] if idx < len(self._Pairs) else ""
        cur  = self._Targets[idx] if idx < len(self._Targets) else ""
        auto = self._AutoTargets[idx] if idx < len(self._AutoTargets) else ""
        if (cur or "") == (src or ""):
            return self.COL_GRAY   # 完全一致 -> 灰
        if (cur or "") == (auto or ""):
            return self.COL_GREEN  # 与自动一致 -> 绿
        return self.COL_RED        # 与自动不一致 -> 红

    def _refresh_view(self):
        # 关键修复：销毁 ListArea 中的**所有**子控件（包括分隔线），
        # 避免多次刷新后残留的 sep 堆积成一块灰色区域
        for w in list(self.ListArea.winfo_children()):
            try: w.destroy()
            except Exception: pass

        self._Rows.clear()
        self._ChkRefs.clear()
        self._SelectedSet.clear()
        self._LastAnchor = None
        self._ViewIdx = []

        only_changed = self.OnlyChangedVar.get()
        for i in self._Order:
            src, _dstcand = self._Pairs[i]
            dst = self._Targets[i] if i < len(self._Targets) else ""
            if only_changed and (not dst or dst == src):
                continue
            self._ViewIdx.append(i)
            self._create_row(i, src, dst)

        self._update_checked_stat()
        self._sync_select_all_state()

    def _create_row(self, idx, src, dst):
        row = Tk.Frame(self.ListArea, bg=self.NORM_BG, padx=6, pady=6)
        row.pack(fill="x", expand=True)

        chk = ttk.Checkbutton(
            row, variable=self._SelVars[idx],
            command=lambda i=idx: self._on_check_toggle(i),
            style="Row.TCheckbutton"
        )
        chk.grid(row=0, column=0, rowspan=2, padx=(0,6), sticky="n")
        self._ChkRefs[idx] = chk

        t1 = Tk.Label(row, text=f"更改前：{src}", anchor="w", bg=self.NORM_BG)
        color = self._color_for(idx)
        t2 = Tk.Label(row, text=f"更改后：{dst}", anchor="w", bg=self.NORM_BG, fg=color)
        t1.grid(row=0, column=1, sticky="w")
        t2.grid(row=1, column=1, sticky="w")

        # 单击：高亮；双击：整行编辑
        for w in (row, t1, t2):
            w.bind("<Button-1>",        lambda e, i=idx: self._on_row_select(i, e))
            w.bind("<Double-Button-1>", lambda e, i=idx: self._edit_target(i))
        # 复选框保持点击切换，不绑定双击

        # 分隔线（1px）
        sep = Tk.Frame(self.ListArea, height=1, bg=self.SEP_BG, bd=0, highlightthickness=0)
        sep.pack(fill="x")

        self._Rows[idx] = row

    def _edit_target(self, idx):
        old = self._Targets[idx]
        win = Tk.Toplevel(self)
        win.title("编辑目标路径（双击行弹出）")
        v = Tk.StringVar(value=old)
        Tk.Entry(win, textvariable=v, width=90).pack(padx=10, pady=10)

        def ok():
            self._Targets[idx] = v.get().strip()
            win.destroy()
            self._refresh_view()  # 重新渲染，颜色按规则更新
        ttk.Button(win, text="确定", command=ok).pack(pady=(0,10))

        win.transient(self.winfo_toplevel())
        win.update_idletasks()
        try:
            w = win.winfo_width(); h = win.winfo_height()
            sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
            x = (sw - w) // 2; y = (sh - h) // 2
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        win.grab_set()
        win.wait_window()

    # ---------- 选择（仅高亮） ----------
    def _on_row_select(self, idx, event):
        shift = bool(event.state & 0x0001)
        ctrl  = bool(event.state & 0x0004)

        if shift and self._LastAnchor is not None:
            a = self._view_pos(self._LastAnchor)
            b = self._view_pos(idx)
            if a is None or b is None:
                self._clear_selection()
                self._set_selected(idx, True)
            else:
                start, end = sorted((a, b))
                if not ctrl: self._clear_selection()
                for pos in range(start, end + 1):
                    self._set_selected(self._ViewIdx[pos], True)
        else:
            if ctrl:
                self._set_selected(idx, not (idx in self._SelectedSet))
            else:
                self._clear_selection()
                self._set_selected(idx, True)

        self._LastAnchor = idx

    def _view_pos(self, full_idx):
        try:
            return self._ViewIdx.index(full_idx)
        except ValueError:
            return None

    def _clear_selection(self):
        for i in list(self._SelectedSet):
            self._paint_selected(i, False)
        self._SelectedSet.clear()

    def _set_selected(self, idx, on: bool):
        if on:  self._SelectedSet.add(idx)
        else:   self._SelectedSet.discard(idx)
        self._paint_selected(idx, on)

    def _paint_selected(self, idx, on: bool):
        row = self._Rows.get(idx)
        if not row: return
        bg = self.HI_BG if on else self.NORM_BG
        row.configure(bg=bg)
        for child in row.winfo_children():
            try:
                if isinstance(child, (Tk.Label, Tk.Frame)):
                    if isinstance(child, Tk.Frame) and child.cget("height") == 1:
                        continue
                    child.configure(bg=bg)
            except Exception:
                pass

    # ---------- 勾选逻辑 ----------
    def _on_check_toggle(self, idx):
        new_state = self._SelVars[idx].get()

        if idx not in self._SelectedSet:
            self._clear_selection()
            self._set_selected(idx, True)
            targets = {idx}
        else:
            targets = self._SelectedSet.copy()

        try:
            self._BulkChecking = True
            for i in targets:
                self._SelVars[i].set(new_state)
        finally:
            self._BulkChecking = False

        self._update_checked_stat()
        self._sync_select_all_state()

    def _update_checked_stat(self):
        visible_total = len(self._ViewIdx)
        checked = 0
        for i in self._ViewIdx:
            try:
                if self._SelVars[i].get():
                    checked += 1
            except Exception:
                pass
        self.CheckedStatVar.set(f"已勾选 {checked} / {visible_total}")

    def _sync_select_all_state(self):
        if not self._ViewIdx:
            self.SelectAllVar.set(False); return
        all_on = all(self._SelVars[i].get() for i in self._ViewIdx)
        self.SelectAllVar.set(bool(all_on))

    def _on_select_all_toggle(self):
        target = bool(self.SelectAllVar.get())
        try:
            self._BulkChecking = True
            for i in self._ViewIdx:
                self._SelVars[i].set(target)
        finally:
            self._BulkChecking = False
        self._update_checked_stat()

    # ---------- 应用 ----------
    def _on_apply(self):
        if not callable(self.OnApply):
            messagebox.showerror("错误", "未绑定 OnApply 回调。"); return
        indices = [i for i in self._ViewIdx if self._SelVars[i].get()]
        if not indices:
            if messagebox.askyesno("提示", "当前未勾选任何项，是否对列表中所有可见项执行？"):
                indices = list(self._ViewIdx)
            else:
                return
        self.OnApply(indices, self._Pairs, self._Targets)
