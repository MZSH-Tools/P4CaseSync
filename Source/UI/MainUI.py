# MainUI.py
# -*- coding: utf-8 -*-

import tkinter as Tk
from tkinter import ttk, messagebox

class MainFrame(ttk.Frame):
    """
    运行界面：
    - SetOnRefresh(handler): handler(Changelist) -> None
    - SetOnApply(handler): handler(Indices, Pairs, Targets) -> None
    - RenderPairs(Pairs, Targets): 回填数据
    - ShowResult(OkCount, FailCount, LogsTail): 显示结果
    """
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.OnRefresh = None
        self.OnApply   = None

        # 顶部：Changelist + 刷新
        top = ttk.Frame(self); top.pack(fill="x", pady=(0,8))
        ttk.Label(top, text="Changelist#:").pack(side="left")
        self.CLVar = Tk.StringVar()
        ttk.Entry(top, textvariable=self.CLVar, width=16).pack(side="left", padx=6)
        ttk.Button(top, text="刷新", command=self._on_refresh).pack(side="left")

        # 过滤
        self.OnlyChangedVar = Tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="仅显示需要修改的文件", variable=self.OnlyChangedVar, command=self._apply_filter).pack(side="left", padx=12)

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

        # 双击右侧项允许用户直接编辑目标路径
        self.RightList.bind("<Double-Button-1>", self._on_edit_target)

    # ------- 回调绑定 -------
    def SetOnRefresh(self, handler):
        self.OnRefresh = handler

    def SetOnApply(self, handler):
        self.OnApply = handler

    # ------- 对外渲染 -------
    def RenderPairs(self, pairs, targets):
        self._Pairs = list(pairs)
        self._Targets = list(targets)
        self._refresh_view()

    def ShowResult(self, ok_count, fail_count, logs_tail):
        self.StatusVar.set(f"完成：成功 {ok_count}，失败 {fail_count}")
        if logs_tail:
            messagebox.showinfo("日志(末尾)", "\n".join(logs_tail[-20:]))

    # ------- 内部逻辑 -------
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

    def _on_refresh(self):
        if not callable(self.OnRefresh):
            messagebox.showerror("错误", "未绑定 OnRefresh 回调。")
            return
        self.OnRefresh(self.CLVar.get().strip())

    def _on_apply(self):
        if not callable(self.OnApply):
            messagebox.showerror("错误", "未绑定 OnApply 回调。")
            return
        # 将当前视图中被选中的行映射回全量索引
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
