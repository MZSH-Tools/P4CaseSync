# Core.py
# -*- coding: utf-8 -*-

import os, re, json, subprocess
from pathlib import Path
from typing import List, Tuple

# ===================== 缓存：Server/User/Client =====================
def _cache_path() -> Path:
    return Path.home() / ".p4_submitlist_tool" / "user.json"

def GetCachedP4User() -> Tuple[str, str, str]:
    # 1) 先读缓存
    cp = _cache_path()
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            s = str(data.get("Server","") or "")
            u = str(data.get("User","") or "")
            c = str(data.get("Client","") or "")
            if any([s,u,c]):
                return (s,u,c)
        except Exception:
            pass
    # 2) p4 set
    server = user = client = ""
    try:
        r = subprocess.run(["p4","set"], capture_output=True, text=True)
        if r.returncode == 0:
            txt = (r.stdout or "") + "\n" + (r.stderr or "")
            def pick(name: str) -> str:
                m = re.search(rf"^{name}\s*=\s*(.+?)(?:\s+\(|\s*$)", txt, flags=re.I|re.M)
                return (m.group(1).strip() if m else "")
            server = pick("P4PORT")
            user   = pick("P4USER")
            client = pick("P4CLIENT")
    except Exception:
        pass
    # 3) env 兜底
    server = server or os.environ.get("P4PORT","")
    user   = user   or os.environ.get("P4USER","")
    client = client or os.environ.get("P4CLIENT","")
    return (server, user, client)

def SaveCachedP4User(server: str, user: str, client: str) -> None:
    cp = _cache_path()
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(
        {"Server": server or "", "User": user or "", "Client": client or ""},
        ensure_ascii=False, indent=2
    ), encoding="utf-8")

# ===================== P4 上下文 =====================
class P4Context:
    """
    封装 p4 命令调用的上下文（Server/User/Client）。
    """
    def __init__(self, Server: str, User: str, Client: str):
        self.Server = Server
        self.User   = User
        self.Client = Client

    def _cmd(self, args: List[str]) -> List[str]:
        base = ["p4", "-p", self.Server, "-u", self.User, "-c", self.Client]
        return base + (args or [])

    def Exec(self, args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(self._cmd(args), text=True, capture_output=True)

    def Test(self) -> Tuple[bool, str]:
        r = self.Exec(["info"])
        ok = (r.returncode == 0)
        msg = (r.stderr or r.stdout or "").strip()
        return ok, msg

    def Login(self, password: str) -> Tuple[bool, str]:
        p = subprocess.Popen(["p4", "-p", self.Server, "-u", self.User, "login"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = p.communicate((password or "") + "\n")
        ok = (p.returncode == 0)
        msg = (err or out or "").strip()
        return ok, msg

# ===================== 名称规范化 & Opened 列表 =====================
def NormalizeName(name: str) -> str:
    """
    简单示例：去除两端空白，保持原大小写；你可以按需要替换为“大小写规则/下划线转驼峰”等。
    """
    return (name or "").strip()

def _parse_opened_lines(text: str) -> List[str]:
    """
    解析 `p4 opened` 输出中的 //depot/... 路径。
    典型行：//depot/Proj/File.txt#3 - edit default change (text)
    """
    out = []
    for line in (text or "").splitlines():
        m = re.match(r"^(//.+?)(?:#\d+)?\s+-\s+\w+\b", line.strip())
        if m:
            out.append(m.group(1))
    return out

def GetOpenedPairs(ctx: P4Context, changelist: str) -> Tuple[bool, List[Tuple[str,str]], List[str], str]:
    """
    返回：
      ok, pairs, targets, msg
      pairs: [(SrcDepot, DstCandidate), ...]
      targets: [DstDepot, ...] —— 初始用 NormalizeName 处理同目录下文件名
    """
    args = ["opened"]
    cl = (changelist or "").strip()
    if cl:
        args += ["-c", cl]
    r = ctx.Exec(args)
    if r.returncode != 0:
        return False, [], [], (r.stderr or r.stdout or "").strip()

    paths = _parse_opened_lines(r.stdout)
    pairs = []
    targets = []
    for dep in paths:
        # 目标：同目录 + 规范化后的文件名（示例规则）
        d = dep.replace("\\", "/")
        dir_ = d.rsplit("/", 1)[0] if "/" in d else d
        base = d.rsplit("/", 1)[-1]
        new_base = NormalizeName(base)
        dst = f"{dir_}/{new_base}" if new_base else d
        pairs.append((d, dst))         # 第二列保留“建议”，仅用于 UI 展示
        targets.append(dst)            # 可被 UI 编辑
    return True, pairs, targets, ""

# ===================== 移动（大小写修正）=====================
def TrySingleMove(ctx: P4Context, src_depot: str, dst_depot: str) -> bool:
    """
    直接 p4 move
    """
    r = ctx.Exec(["move", src_depot, dst_depot])
    return r.returncode == 0

def TryTwoMoves(ctx: P4Context, src_depot: str, dst_depot: str) -> bool:
    """
    两步法：src -> temp -> dst，用于大小写不敏感文件系统修正。
    """
    dir_ = os.path.dirname(dst_depot).replace("\\", "/")
    base = os.path.basename(dst_depot)
    temp_name = f"{base}.__tmp__"
    temp_depot = f"{dir_}/{temp_name}" if dir_ else f"/{temp_name}"
    r1 = ctx.Exec(["move", src_depot, temp_depot])
    if r1.returncode != 0:
        return False
    r2 = ctx.Exec(["move", temp_depot, dst_depot])
    return r2.returncode == 0
