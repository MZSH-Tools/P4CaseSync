# MainUI.py
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

class MainFrame(ttk.Frame):
    """
    单列列表（两行显示：更改前/更改后）+ 勾选 + 多选 + 进度
    选择仅影响高亮；点击勾选会把“当前已选择的所有行”的勾选状态批量改为该勾选的新状态。
    API:
      - SetOnListChangelists(fn)  -> 列出 changelists
      - SetOnRefresh(fn)          -> 根据 changelist 刷新列表
      - SetOnApply(fn)            -> 应用勾选的项
      - RenderPairs(pairs, targets)
      - ShowResult(ok, fail, logs_tail)
      - StartProgress/UpdateProgress/EndProgress
    """

    HI_BG   = "#e6f2ff"   # 高亮背景
    NORM_BG = "#f8f8f8"   # 行容器默认背景

    def __init__(self, master):
        super().__init__(master, padding=8)
        self.OnListChangelists = None
        self.OnRefresh = None
        self.OnApply   = None

        # 顶部：Changelist 下拉 + 过滤 + 全选/全不选 + 勾选计数
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
                        command=self._apply_filter).pack(side="left", padx=(12,6))

        ttk.Button(top, text="全选可见", command=self._check_all_visible).pack(side="left")
        ttk.Button(top, text="全不选可见", command=self._uncheck_all_visible).pack(side="left", padx=(6,0))

        self.CheckedStatVar = Tk.StringVar(value="已选中 0 / 0")
        ttk.Label(top, textvariable=self.CheckedStatVar).pack(side="right")

        # 中部：滚动区域（单列）
        mid = ttk.Frame(self); mid.pack(fill="both", expand=True)
        self.Canvas = Tk.Canvas(mid, highlightthickness=0)
        vbar = ttk.Scrollbar(mid, orient="vertical", command=self.Canvas.yview)
        self.Canvas.configure(yscrollcommand=vbar.set)
        self.Canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="left", fill="y")

        self.ListArea = Tk.Frame(self.Canvas, bg=self.NORM_BG)
        self._canvas_item = self.Canvas.create_window((0, 0), window=self.ListArea, anchor="nw")
        self.ListArea.bind("<Configure>", lambda e: self.Canvas.configure(scrollregion=self.Canvas.bbox("all")))
        self.Canvas.bind("<Configure>", self._on_canvas_resize)

        # 底部：应用 + 进度
        bottom = ttk.Frame(self); bottom.pack(fill="x", pady=(8,0))
        ttk.Button(bottom, text="应用修改", command=self._on_apply).pack(side="right")

        progBox = ttk.Frame(bottom); progBox.pack(side="left", fill="x", expand=True)
        self.ProgressTextVar = Tk.StringVar(value="就绪")
        ttk.Label(progBox, textvariable=self.ProgressTextVar).pack(anchor="w")
        self.ProgressBar = ttk.Progressbar(progBox, orient="horizontal", mode="determinate")
        self.ProgressBar.pack(fill="x", expand=True, pady=(2,0))

        # 数据缓存/状态
        self._Pairs   = []   # [(src, dstCand), ...]
        self._Targets = []   # [dst, ...]
        self._Order   = []   # 排序后的全量索引列表
        self._ViewIdx = []   # 可见 -> 全量
        self._SelVars = []   # 与全量对齐的 BooleanVar（勾选）
        self._Rows    = {}   # {full_idx: rowFrame}
        self._SelectedSet = set()   # “高亮选择”的 full_idx 集合
        self._LastAnchor  = None    # Shift 锚点
        self._BulkChecking = False  # 批量设置勾选时避免递归

        # 下拉内容
        self._CLItems = []
        self._CLLabelToId = {}
        self._set_cl_items([("default", "default (未提交)")])
        self.CLCombo.set("default (未提交)")

    # ---------- 回调绑定 ----------
    def SetOnListChangelists(self, fn): self.OnListChangelists = fn
    def SetOnRefresh(self, fn):         self.OnRefresh = fn
    def SetOnApply(self, fn):           self.OnApply = fn

    # ---------- 对外渲染 ----------
    def RenderPairs(self, pairs, targets):
        self._Pairs   = list(pairs)
        self._Targets = list(targets)

        # 初始化/扩展勾选变量（默认勾选）
        n = len(self._Pairs)
        if len(self._SelVars) < n:
            for _ in range(n - len(self._SelVars)):
                self._SelVars.append(Tk.BooleanVar(value=True))

        # —— 自动排序（优先更改后文件名，其次更改后完整路径）——
        keys = []
        for i, (src, _dstcand) in enumerate(self._Pairs):
            dst  = self._Targets[i] if i < len(self._Targets) else ""
            name = _basename(dst) or _basename(src)
            keys.append((_natural_key(name), _natural_key(dst or ""), i))
        keys.sort()
        self._Order = [i for (_k1, _k2, i) in keys]

        self._refresh_view()

    def ShowResult(self, ok_count, fail_count, logs_tail):
        self.ProgressTextVar.set(f"完成：成功 {ok_count}，失败 {fail_count}")
        self.ProgressBar.stop(); self.ProgressBar["value"] = 0
        if logs_tail:
            messagebox.showinfo("日志(末尾)", "\n".join(logs_tail[-20:]))

    # ---------- 进度 ----------
    def StartProgress(self, total:int):
        self.ProgressBar["mode"] = "determinate"
        self.ProgressBar["maximum"] = max(1, total)
        self.ProgressBar["value"] = 0
        self.ProgressTextVar.set(f"开始转换：0/{total}")

    def UpdateProgress(self, done:int, total:int, msg:str = ""):
        self.ProgressBar["value"] = done
        text = f"正在转换 {done}/{total}"
        if msg: text += f"  {msg}"
        self.ProgressTextVar.set(text)
        self.update_idletasks()

    def EndProgress(self):
        self.ProgressTextVar.set("转换完成")
        self.ProgressBar["value"] = self.ProgressBar["maximum"]

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

    def _refresh_view(self):
        # 清空旧行 & 选择
        for w in self._Rows.values():
            try: w.destroy()
            except Exception: pass
        self._Rows.clear()
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

    def _create_row(self, idx, src, dst):
        row = Tk.Frame(self.ListArea, bg=self.NORM_BG, padx=6, pady=6)
        row.pack(fill="x", expand=True)

        # 勾选框（点击时：把“当前已选择的所有行”的勾选统一为本次的新状态）
        chk = ttk.Checkbutton(row, variable=self._SelVars[idx],
                              command=lambda i=idx: self._on_check_toggle(i))
        chk.grid(row=0, column=0, rowspan=2, padx=(0,6), sticky="n")

        # 两行文本
        t1 = Tk.Label(row, text=f"更改前：{src}", anchor="w", bg=self.NORM_BG)
        t2 = Tk.Label(row, text=f"更改后：{dst}", anchor="w", bg=self.NORM_BG, fg="#2a6f2a")
        t1.grid(row=0, column=1, sticky="w")
        t2.grid(row=1, column=1, sticky="w")

        # 行选择（仅改变高亮，不触发勾选变化）
        for w in (row, t1, t2):
            w.bind("<Button-1>", lambda e, i=idx: self._on_row_select(i, e))

        # 分割线
        sep = ttk.Separator(self.ListArea, orient="horizontal")
        sep.pack(fill="x")

        self._Rows[idx] = row

    # ---------- 选择（高亮）逻辑 ----------
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
                if not ctrl:
                    self._clear_selection()
                for pos in range(start, end + 1):
                    self._set_selected(self._ViewIdx[pos], True)
        else:
            if ctrl:
                self._set_selected(idx, not (idx in self._SelectedSet))
            else:
                self._clear_selection()
                self._set_selected(idx, True)

        self._LastAnchor = idx  # 更新锚点

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
        if on:
            self._SelectedSet.add(idx)
        else:
            self._SelectedSet.discard(idx)
        self._paint_selected(idx, on)

    def _paint_selected(self, idx, on: bool):
        row = self._Rows.get(idx)
        if not row: return
        bg = self.HI_BG if on else self.NORM_BG
        row.configure(bg=bg)
        for child in row.winfo_children():
            try:
                if isinstance(child, Tk.Label):
                    child.configure(bg=bg)
            except Exception:
                pass

    # ---------- 勾选（Check）逻辑 ----------
    def _on_check_toggle(self, idx):
        """
        点击某一行的勾选框：
        - 若该行不在当前选择集：先清空选择→仅选中该行→按新状态设置（只改这一行）
        - 若该行在当前选择集：把当前“已选择的所有行”的勾选状态统一成该行的新状态
        """
        # 勾选框已经把自身变量切到新状态了
        new_state = self._SelVars[idx].get()

        # 规则：只有在“修改自己（位于选择集内）”时才保留选择集
        if idx not in self._SelectedSet:
            # 不在选择集：改为单选该行
            self._clear_selection()
            self._set_selected(idx, True)
            targets = {idx}
        else:
            # 在选择集：批量应用到已选择的所有行
            targets = self._SelectedSet.copy()

        # 批量写入勾选变量（避免递归触发 command）
        try:
            self._BulkChecking = True
            for i in targets:
                self._SelVars[i].set(new_state)
        finally:
            self._BulkChecking = False

        self._update_checked_stat()


    def _update_checked_stat(self):
        visible_total = len(self._ViewIdx)
        checked = 0
        for i in self._ViewIdx:
            try:
                if self._SelVars[i].get():
                    checked += 1
            except Exception:
                pass
        self.CheckedStatVar.set(f"已选中 {checked} / {visible_total}")

    # ---------- 顶部按钮（全选/全不选 → 勾选） ----------
    def _check_all_visible(self):
        try:
            self._BulkChecking = True
            for i in self._ViewIdx:
                self._SelVars[i].set(True)
        finally:
            self._BulkChecking = False
        self._update_checked_stat()

    def _uncheck_all_visible(self):
        try:
            self._BulkChecking = True
            for i in self._ViewIdx:
                self._SelVars[i].set(False)
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
