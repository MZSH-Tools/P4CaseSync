# MainUI.py
# -*- coding: utf-8 -*-

import os
import tkinter as Tk
from tkinter import ttk, messagebox, simpledialog
from typing import List, Tuple

class MainFrame(ttk.Frame):
    """
    正常运行界面：
    - SetOnRefresh(handler): handler(Changelist) -> None
    - SetOnApply(handler): handler(Indices, Pairs, Targets) -> None
    - RenderPairs(Pairs, Targets): 由外部(Main)回填数据
    - ShowResult(OkCount, FailCount, LogsTail): 外部调用显示结果
    """
    def __init__(self, Master):
        super().__init__(Master, padding=8)

        self.OnRefreshHandler = None
        self.OnApplyHandler   = None

        # 顶部栏
        Top = ttk.Frame(self); Top.pack(fill="x", padx=4, pady=4)
        ttk.Label(Top, text="Changelist:").pack(side="left")

        self.ClVar = Tk.StringVar(value="default")
        self.ClCombo = ttk.Combobox(Top, textvariable=self.ClVar, width=18, state="readonly")
        self.ClCombo.pack(side="left", padx=(6,12))

        self.OnlyDiffVar = Tk.BooleanVar(value=True)
        ttk.Checkbutton(Top, text="仅显示需要修改的文件", variable=self.OnlyDiffVar,
                        command=self.OnRefreshClicked).pack(side="left")

        ttk.Button(Top, text="刷新", command=self.OnRefreshClicked).pack(side="right")

        # 中部：左右列表
        Mid = ttk.Frame(self); Mid.pack(fill="both", expand=True)
        Left = ttk.Frame(Mid); Left.pack(side="left", fill="both", expand=True, padx=(0,4))
        Right = ttk.Frame(Mid); Right.pack(side="left", fill="both", expand=True, padx=(4,0))

        ttk.Label(Left, text="Depot 路径（当前）").pack(anchor="w")
        ttk.Label(Right, text="目标命名（双击编辑文件名）").pack(anchor="w")

        self.LeftTree = ttk.Treeview(Left, columns=("Depot",), show="headings", selectmode="extended")
        self.LeftTree.heading("Depot", text="depot path")
        self.LeftTree.pack(fill="both", expand=True)

        self.RightTree = ttk.Treeview(Right, columns=("Target",), show="headings", selectmode="extended")
        self.RightTree.heading("Target", text="target name")
        self.RightTree.pack(fill="both", expand=True)

        # 底部：操作按钮
        Bottom = ttk.Frame(self); Bottom.pack(fill="x", padx=4, pady=4)
        ttk.Button(Bottom, text="应用（选中）", command=lambda: self.OnApplyClicked(True)).pack(side="right")
        ttk.Button(Bottom, text="应用（全部）", command=lambda: self.OnApplyClicked(False)).pack(side="right", padx=(0,6))

        # 数据
        self.Pairs: List[Tuple[str, str]] = []
        self.TargetNames: List[str] = []

        self.BindEvents()

    # ------- 外部绑定 -------
    def SetOnRefresh(self, Handler):
        self.OnRefreshHandler = Handler

    def SetOnApply(self, Handler):
        self.OnApplyHandler = Handler

    # ------- 事件绑定 -------
    def BindEvents(self):
        def OnEdit(Event):
            Item = self.RightTree.focus()
            if not Item:
                return
            Idx = int(self.RightTree.item(Item, "tags")[0])
            Current = self.TargetNames[Idx]
            NewName = simpledialog.askstring("编辑目标文件名", "仅修改文件名（不含路径）:", initialvalue=Current)
            if not NewName:
                return
            if any(Ch in NewName for Ch in '<>:"|?*'):
                messagebox.showwarning("非法字符", "文件名包含非法字符。")
                return
            self.TargetNames[Idx] = NewName
            self.RenderRows()
        self.RightTree.bind("<Double-1>", OnEdit)

    # ------- 按钮事件 -------
    def OnRefreshClicked(self):
        if self.OnRefreshHandler is None:
            messagebox.showerror("错误", "未绑定 OnRefresh 回调。")
            return
        Changelist = self.ClVar.get() or "default"
        self.OnRefreshHandler(Changelist)

    def OnApplyClicked(self, UseSelection: bool):
        if self.OnApplyHandler is None:
            messagebox.showerror("错误", "未绑定 OnApply 回调。")
            return
        if not self.Pairs:
            messagebox.showinfo("提示", "没有可处理的文件。")
            return

        Indices = list(range(len(self.Pairs)))
        if UseSelection:
            SelTags = {T for I in self.RightTree.selection() for T in self.RightTree.item(I, "tags")}
            if not SelTags:
                messagebox.showinfo("提示", "未选择任何项。")
                return
            Indices = [int(T) for T in SelTags]

        self.OnApplyHandler(Indices, self.Pairs, self.TargetNames)

    # ------- 外部可调用 -------
    def RenderPairs(self, Pairs: List[Tuple[str, str]], Targets: List[str]):
        self.Pairs = Pairs
        self.TargetNames = Targets
        self.RenderRows()

    def RenderRows(self):
        self.LeftTree.delete(*self.LeftTree.get_children())
        self.RightTree.delete(*self.RightTree.get_children())
        OnlyDiff = self.OnlyDiffVar.get()
        for Idx, (Depot, _Local) in enumerate(self.Pairs):
            Target = self.TargetNames[Idx]
            if OnlyDiff:
                Base = os.path.basename(Depot).replace("\\", "/")
                if Base == Target:
                    continue
            Tag = (str(Idx),)
            self.LeftTree.insert("", "end", values=(Depot,), tags=Tag)
            self.RightTree.insert("", "end", values=(Target,), tags=Tag)

    def ShowResult(self, OkCount: int, FailCount: int, LogsTail: List[str]):
        messagebox.showinfo("处理完成", f"成功：{OkCount}，失败：{FailCount}\n\n" + "\n".join(LogsTail))
