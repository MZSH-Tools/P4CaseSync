# MainUI.py
# -*- coding: utf-8 -*-

import tkinter as Tk
from tkinter import ttk, messagebox

class MainFrame(ttk.Frame):
    """
    运行界面（精简版）：
    - SetOnListChangelists(fn):  fn() -> List[Tuple[str, str]]
        返回 [("default", "default (未提交)"), ("12345", "12345 - 描述"), ...]
        第一个值是changlist标识(数字或"default")，第二个是展示文本
    - SetOnRefresh(fn):          fn(ChangelistId: str) -> None
    - SetOnApply(fn):            fn(Indices, Pairs, Targets) -> None
    - RenderPairs(Pairs, Targets)
    - ShowResult(OkCount, FailCount, LogsTail)
    """
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.OnListChangelists = None
        self.OnRefresh = None
        self.OnApply   = None

        # 顶部：Changelist 下拉选择（点击下拉时自动刷新）
        top = ttk.Frame(self); top.pack(fill="x", pady=(0,8))
        ttk.Label(top, text="Changelist#:").pack(side="left")

        self.CLVar = Tk.StringVar()
        # postcommand 会在每次展开下拉前调用 → 最新化列表
        self.CLCombo = ttk.Combobox(
            top, textvariable=self.CLVar, state="readonly", width=48,
            postcommand=self._refresh_changelist_options
        )
        self.CLCombo.pack(side="left", padx=6, fill="x", expand=True)

        # 选中后，自动触发刷新
        self.CLCombo.bind("<<ComboboxSelected>>", self._on_cl_selected)

        # 过滤
        self.OnlyChangedVar = Tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top, text="仅显示需要修改的文件",
            variable=self.OnlyChangedVar, command=self._apply_filter
        ).pack(side="left", padx=12)

        # 中部：左右两列（原路径 / 目标路径）
        mid = ttk.Frame(self); mid.pack(fill="both", expand=True)

        left = ttk.LabelFrame(mid, text="原路径"); left.pack(side="left", fill="both", expand=True, padx=(0,4))
        right= ttk.LabelFrame(mid, text="修改后路径"); right.pack(side="left", fill="both", expand=True, padx=(4,0))

        self.LeftList  = Tk.Listbox(left, height=20, selectmode="extended")
        self.RightList = Tk.Listbox(right, height=20, selectmode="extended")
        self.LeftList.pack(fill="both", expand=True, padx=6, pady=6)
        self.RightList.pack(fill="both", expand=True, padx=6, pady=6)

        # 底部：应用
        bottom = ttk.Frame(self); bottom.pack(fill="x", pady=(8,0))
        ttk.Button(bottom, text="应用修改", command=self._on_apply).pack(side="right")

        # 状态/日志
        self.StatusVar = Tk.StringVar(value="")
        ttk.Label(self, textvariable=self.StatusVar, foreground="#008000").pack(anchor="w", pady=(6,0))

        # 数据缓存
        self._Pairs   = []  # [(SrcDepot, DstCandidate), ...]
        self._Targets = []  # [DstDepot, ...]
        self._ViewIdx = []  # 视图中的行对应 self._Pairs 的索引

        # Changelist 下拉显示映射：展示文本 -> 实际ID
        self._CLItems = []           # [(id, label)]
        self._CLLabelToId = {}       # {label: id}

        # 双击右侧项允许用户直接编辑目标路径
        self.RightList.bind("<Double-Button-1>", self._on_edit_target)

        # 初始显示 default（不触发远程刷新；第一次点击下拉再拉取最新）
        self._set_cl_items([("default", "default (未提交)")])
        self.CLCombo.set("default (未提交)")

    # ------- 回调绑定 -------
    def SetOnListChangelists(self, fn):
        self.OnListChangelists = fn

    def SetOnRefresh(self, fn):
        self.OnRefresh = fn

    def SetOnApply(self, fn):
        self.OnApply = fn

    # ------- 对外渲染 -------
    def RenderPairs(self, pairs, targets):
        self._Pairs = list(pairs)
        self._Targets = list(targets)
        self._refresh_view()

    def ShowResult(self, ok_count, fail_count, logs_tail):
        self.StatusVar.set(f"完成：成功 {ok_count}，失败 {fail_count}")
        if logs_tail:
            messagebox.showinfo("日志(末尾)", "\n".join(logs_tail[-20:]))

    # ------- 内部：Changelist 列表 -------
    def _set_cl_items(self, items):
        """items: [(id, label)]"""
        self._CLItems = list(items)
        self._CLLabelToId = {label: id_ for (id_, label) in self._CLItems}
        self.CLCombo["values"] = [label for (_id, label) in self._CLItems]

    def _refresh_changelist_options(self):
        """在下拉展开前调用，拉最新 changelist 列表"""
        if not callable(self.OnListChangelists):
            return
        try:
            items = self.OnListChangelists() or []
        except Exception:
            items = []
        # 保证 default 总是在第一项
        seen_default = any(i[0] == "default" for i in items)
        if not seen_default:
            items = [("default", "default (未提交)")] + items
        else:
            # 将 default 移到第一项
            items = [i for i in items if i[0] == "default"] + [i for i in items if i[0] != "default"]
        self._set_cl_items(items)

    def _on_cl_selected(self, _evt=None):
        """选择某个 changelist 后，立即刷新内容"""
        if not callable(self.OnRefresh):
            messagebox.showerror("错误", "未绑定 OnRefresh 回调。")
            return
        label = self.CLVar.get()
        cl_id = self._CLLabelToId.get(label, "default")
        self.OnRefresh(cl_id)

    # ------- 内部：列表视图 -------
    def _refresh_view(self):
        self.LeftList.delete(0, Tk.END)
        self.RightList.delete(0, Tk.END)
        self._ViewIdx = []

        only_changed = self.OnlyChangedVar.get()
        for i,(src,_dstc) in enumerate(self._Pairs):
            dst = self._Targets[i] if i < len(self._Targets) else ""
            if only_changed and (not dst or dst == src):
                continue
            self._ViewIdx.append(i)
            self.LeftList.insert(Tk.END, src)
            self.RightList.insert(Tk.END, dst)

    def _apply_filter(self):
        self._refresh_view()

    def _on_apply(self):
        if not callable(self.OnApply):
            messagebox.showerror("错误", "未绑定 OnApply 回调。")
            return
        # 当前视图中被选中的行映射回全量索引
        sel = list(self.RightList.curselection())
        if not sel:
            sel = list(range(self.RightList.size()))  # 未选择则默认全部视图项
        indices = [self._ViewIdx[i] for i in sel]
        self.OnApply(indices, self._Pairs, self._Targets)

    def _on_edit_target(self, _evt):
        # 简单编辑器：把右侧选择的项替换为用户输入
        idxs = self.RightList.curselection()
        if not idxs:
            return
        i_view = idxs[0]
        i_full = self._ViewIdx[i_view]
        old = self._Targets[i_full]
        win = Tk.Toplevel(self)
        win.title("编辑目标路径")
        v = Tk.StringVar(value=old)
        Tk.Entry(win, textvariable=v, width=80).pack(padx=8, pady=8)
        def ok():
            self._Targets[i_full] = v.get().strip()
            self._refresh_view()
            win.destroy()
        ttk.Button(win, text="确定", command=ok).pack(pady=(0,8))
