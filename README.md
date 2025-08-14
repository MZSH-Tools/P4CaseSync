# P4CaseSync

P4CaseSync 是一个针对 Perforce (Helix Core) 的本地工具，  
用于在提交前将 depot 中的文件名大小写同步为本地文件系统的实际命名。  

它特别适用于服务器大小写模式为 `insensitive` 的情况，  
确保提交记录中的文件名大小写与本地保持一致，从而避免在跨平台或大小写敏感的构建环境中出现问题。  

主要功能：  
- 自动检测 Changelist 中 depot 与本地文件名大小写不一致的文件  
- 先尝试一次 `p4 move` 修正大小写，失败时自动使用两步改名策略  
- 支持 GUI 操作，提供进度条和日志输出  
- 可选自动提交（Auto Submit）与 Dry Run 模式  
- 缓存常用连接信息，减少重复输入  

## 许可证
本项目基于 MIT License 开源。
