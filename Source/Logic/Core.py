# -*- coding: utf-8 -*-

import os, re, json, subprocess
from pathlib import Path
from typing import List, Tuple, Optional

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

# ===================== 名称规范化 & Opened 解析 =====================
def NormalizeName(name: str) -> str:
    # 可在这里扩展大小写/非法字符处理规则；当前仅 strip
    return (name or "").strip()

def _parse_opened_lines(text: str) -> List[Tuple[str, str]]:
    """
    解析 p4 opened 输出。
    返回: [(depot_path, action), ...]
      例：//depot/Path/File.uasset#3 - edit default change (text)
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

# ===================== where & 路径大小写纠正 =====================
def _p4_where(ctx: P4Context, any_path: str) -> Optional[Tuple[str, str, str]]:
    """
    调用 `p4 where <path>`，<path> 可以是 depot/client/local 任意一种。
    返回 (depotPath, clientPath, localPath)；失败返回 None。
    只取第一行映射（多数工作区场景足够）。
    """
    r = ctx.Exec(["where", any_path])
    if r.returncode != 0:
        return None
    line = (r.stdout or "").strip().splitlines()[0].strip()
    # depot client local  —— client 不含空格，local 可能含空格
    m = re.match(r"^(//\S+)\s+(//\S+)\s+(.+)$", line)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)

def _listdir_safe(path: str) -> List[str]:
    try:
        return os.listdir(path or os.sep)
    except Exception:
        return []

def _correct_case_along_path(local_path: str) -> str:
    """
    逐级把 local_path 纠正为“磁盘上的真实大小写”。
    即使尾部不存在，也会尽量纠正到能访问到的最深父目录。
    """
    if not local_path:
        return local_path

    p = Path(local_path)
    parts = list(p.parts)
    if not parts:
        return local_path

    # Windows 盘符单独处理（比如 'C:\\'）
    acc = Path(parts[0])
    for name in parts[1:]:
        parent = str(acc)
        entries = _listdir_safe(parent)
        fixed = next((e for e in entries if e.lower() == (name or "").lower()), name)
        acc = acc / fixed
    return str(acc)

def _split_ns_root(ns_path: str) -> Tuple[str, List[str]]:
    """
    将 //xxx/aa/bb 拆成 ('//xxx', ['aa','bb'])
    仅用于 depot/client 命名空间路径。
    """
    if not ns_path.startswith("//"):
        return "", []
    parts = ns_path[2:].split("/")
    if not parts:
        return ns_path, []
    root = "//" + parts[0]
    tail = parts[1:]
    return root, tail

def _apply_full_local_case_to_depot(depot_path: str, client_path: str, local_cased: str) -> str:
    """
    使用“本地真实大小写”修正整个 depot 目标路径的所有层级：
      - 通过 where 得到 depot/client/local 三者；
      - 以 client 的尾部层级数为准，从 local_cased 末尾取同样数量的层级，与 depot 尾部一一对应；
      - 用 local_cased 的每一层名称（真实大小写）替换 depot 尾部对应层级；
      - depot 根（//depotRoot）保持不变。
    """
    d_root, d_tail = _split_ns_root(depot_path)
    c_root, c_tail = _split_ns_root(client_path)

    # local_cased 的尾部（与 client 层数对齐）
    l_parts = list(Path(local_cased).parts)
    # 去掉盘符或根（Windows 盘符： 'C:\\'；类 Unix 根：'/'）
    if l_parts and (l_parts[0].endswith(":\\") or l_parts[0] == os.sep or l_parts[0].endswith(":")):
        l_tail = l_parts[1:]
    else:
        l_tail = l_parts[:]

    # 取最后 len(c_tail) 个作为 client 对应尾部
    tail_len = min(len(d_tail), len(c_tail), len(l_tail))
    if tail_len <= 0:
        return depot_path  # 无法安全映射则返回原值

    l_tail_use = l_tail[-tail_len:]
    new_tail = []
    for i in range(tail_len):
        local_name = l_tail_use[i]
        new_tail.append(local_name if local_name else d_tail[-tail_len + i])

    # 如果 depot 比 client 更深（极少见），保留更高层不变 + 未覆盖的前缀
    if len(d_tail) > tail_len:
        prefix = d_tail[:-tail_len]
        d_tail_final = prefix + new_tail
    else:
        d_tail_final = new_tail

    return d_root + "/" + "/".join(d_tail_final)

# ===================== Opened 列表（以本地为准生成“更改后”） =====================
def GetOpenedPairs(ctx: P4Context, changelist: str) -> Tuple[bool, List[Tuple[str,str]], List[str], str]:
    """
    ok, pairs, targets, msg
    - changelist 可为 "" / "default" / "12345"
    - 仅返回 {edit, add, move/add}，过滤 delete/move/delete 等
    - “更改后”默认来自**本地真实大小写**（整条路径全部层级纠正），然后回写为 depot 目标路径
      * 若 where 或本地访问失败，则降级：只对文件名做 NormalizeName
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

        dep = dep.replace("\\", "/")
        ddir = dep.rsplit("/", 1)[0] if "/" in dep else dep
        dbase = dep.rsplit("/", 1)[-1]

        # 先构造一个保底目标（仅文件名规范化），以便 where 失败时回退
        new_base = NormalizeName(dbase)
        dst_fallback = f"{ddir}/{new_base}" if new_base else dep

        # 用 where 获取本地与 client，并用本地真实大小写修正“整条路径”
        where_info = _p4_where(ctx, dep)
        if not where_info:
            pairs.append((dep, dst_fallback)); targets.append(dst_fallback); continue

        depot0, client0, local0 = where_info
        if not local0:
            pairs.append((dep, dst_fallback)); targets.append(dst_fallback); continue

        local_cased = _correct_case_along_path(local0)
        # 用本地真实大小写的每一层，映射回 depot 尾部所有层级（根保持不变）
        dst = _apply_full_local_case_to_depot(depot0, client0, local_cased) or dst_fallback

        pairs.append((dep, dst))
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
