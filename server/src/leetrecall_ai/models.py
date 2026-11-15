"""Card data model — a 1:1 mirror of the extension's `blankCard()` in src/store.js.

`extra="allow"` on Card is deliberate: the extension merges arbitrary fields on save
(`upsertCard`), so the backend must round-trip fields it doesn't know about instead of
silently dropping them when a card is synced back.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Keep in sync with PATTERN_PRESETS in src/store.js (tests/test_patterns.py enforces this).
PATTERN_PRESETS: tuple[str, ...] = (
    "双指针", "滑动窗口", "二分查找", "前缀和", "差分", "哈希表", "单调栈", "单调队列",
    "堆/优先队列", "BFS", "DFS/回溯", "拓扑排序", "并查集", "最短路", "动态规划", "区间DP",
    "背包", "状态压缩", "贪心", "排序", "链表技巧", "树的遍历", "二叉搜索树", "Trie",
    "线段树/树状数组", "位运算", "数学", "模拟", "字符串匹配", "设计",
)


class Schedule(BaseModel):
    """FSRS state (src/fsrs.js newSchedule). Times are epoch milliseconds."""

    state: str = "new"  # new | review | relearning
    s: float = 0  # stability (days)
    d: float = 0  # difficulty 1..10
    due: int = 0
    last: int = 0
    reps: int = 0
    lapses: int = 0


class HistoryEntry(BaseModel):
    t: int  # epoch ms
    g: int  # rating 1=Again 2=Hard 3=Good 4=Easy
    mode: str = "card"  # "solve" = rated right after AC, "card" = flip-card review
    wasNew: bool = False


class SolveStats(BaseModel):
    attempts: int = 0
    lastSolveMinutes: int | None = None


class Card(BaseModel):
    model_config = ConfigDict(extra="allow")

    slug: str
    id: str = ""
    title: str = ""
    titleCn: str = ""
    difficulty: str = ""
    tags: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    idea: str = ""
    complexity: str = ""
    pitfalls: str = ""
    code: str = ""
    lang: str = ""
    site: str = "com"
    createdAt: int = 0
    updatedAt: int = 0
    suspended: bool = False
    sched: Schedule = Field(default_factory=Schedule)
    history: list[HistoryEntry] = Field(default_factory=list)
    stats: SolveStats = Field(default_factory=SolveStats)
