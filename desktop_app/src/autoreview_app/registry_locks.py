"""进程级注册表写锁(opus 评审 C1:写路径必须全员持锁,缺一处即 last-writer-wins)。

两本注册表、两把锁(分文件,互不阻塞):
- ELEMENTS_REGISTRY_LOCK   : data/elements/registry.json 的所有「读-改-存」段
  (导入归一、bootstrap 尾巴、PUT /elements 人工改名/合并)。
- INSTITUTIONS_REGISTRY_LOCK: data/institutions/registry.json(authorship populate;
  整跑持锁——只有 populate 写它,串行化双击重跑即可,不挡要素导入)。

加新写路径时:先到这里拿锁,再 load_registry;save_registry 之后才释放。
"""
from __future__ import annotations

import threading

ELEMENTS_REGISTRY_LOCK = threading.Lock()
INSTITUTIONS_REGISTRY_LOCK = threading.Lock()
