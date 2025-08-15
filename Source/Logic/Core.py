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

# ===================== Changelist 列表（待提交）=====================
def GetPendingChangelists(ctx: P4Context, Max: int = 50) -> List[Tuple[str, str]]:
    """
    获取当前工作区的“待提交” changelist 列表（不含已提交），用于下拉选择。
    返回: [(id, label), ...]
        id: "default" 或 数字字符串
        label: 用于 UI 展示，如 "12345 - 修复命名大小写"
    """
    out: List[Tuple[str, str]] = []
    # p4 changes -c <client> -s pending -m N
    r = ctx.Exec(["changes", "-c", ctx.Client, "-s", "pending", "-m", str(Max)])
    if r.returncode != 0:
        return out
    # 行示例：Change 12345 on 2025/08/10 by user@client 'desc...'
    for line in (r.stdout or "").splitlines():
        m = re.match(r"^Change\s+(\d+)\s+on\s+.+? by .+? '(.+)'", line.strip())
        if not m:
            continue
        cl = m.group(1)
        desc = (m.group(2) or "").strip()
        label = f"{cl} - {desc}"
        out.append((cl, label))
    return out

# ===================== 名称规范化 & Opened 列表 =====================
def NormalizeName(name: str) -> str:
    # 你可以在这里扩展大小写/非法字符处理规则；当前仅 strip
    return (name or "").strip()

def _parse_opened_lines(text: str):
    """
    解析 p4 opened 输出。
    返回: [(depot_path, action), ...]
      例行: //depot/Path/File.uasset#3 - edit default change (text)
    """
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        m = re.match(r"^(//.+?)(?:#\d+)?\s+-\s+([a-zA-Z/]+)\b", s)
        if m:
            depot = m.group(1)
            action = (m.group(2) or "").lower()
            out.append((depot, action))
    return out

def GetOpenedPairs(ctx: P4Context, changelist: str) -> Tuple[bool, List[Tuple[str,str]], List[str], str]:
    """
    ok, pairs, targets, msg
    - changelist 可为 "" / "default" / "12345"
    - 仅返回 {edit, add, move/add}，过滤 delete/move/delete 等
    - 目标路径（“更改后”）基于 depot 路径目录 + 规范化后的文件名，不读取本地路径
    """
    args = ["opened"]
    cl = (changelist or "").strip()
    if cl and cl != "default":
        args += ["-c", cl]
    r = ctx.Exec(args)
    if r.returncode != 0:
        return False, [], [], (r.stderr or r.stdout or "").strip()

    paths_actions = _parse_opened_lines(r.stdout)
    pairs: List[Tuple[str, str]] = []
    targets: List[str] = []

    allowed = {"edit", "add", "move/add"}
    for dep, action in paths_actions:
        if action not in allowed:
            continue
        d = dep.replace("\\", "/")
        dir_ = d.rsplit("/", 1)[0] if "/" in d else d
        base = d.rsplit("/", 1)[-1]
        new_base = NormalizeName(base)
        dst = f"{dir_}/{new_base}" if new_base else d
        pairs.append((d, dst))
        targets.append(dst)
    return True, pairs, targets, ""

# ===================== 移动（大小写修正）=====================
def TrySingleMove(ctx: P4Context, src_depot: str, dst_depot: str) -> bool:
    r = ctx.Exec(["move", src_depot, dst_depot])
    return r.returncode == 0

def TryTwoMoves(ctx: P4Context, src_depot: str, dst_depot: str) -> bool:
    dir_ = os.path.dirname(dst_depot).replace("\\", "/")
    base = os.path.basename(dst_depot)
    temp_name = f"{base}.__tmp__"
    temp_depot = f"{dir_}/{temp_name}" if dir_ else f"/{temp_name}"
    r1 = ctx.Exec(["move", src_depot, temp_depot])
    if r1.returncode != 0:
        return False
    r2 = ctx.Exec(["move", temp_depot, dst_depot])
    return r2.returncode == 0
