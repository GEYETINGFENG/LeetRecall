"""Sanity-check every seed solution (library + eval) against small hand-written cases.

Run:  python3 server/data/test_solutions.py
Solutions are written LeetCode-style (no imports), so we exec them with LeetCode's implicit prelude.
"""
import bisect
import collections
import heapq
import math
import sys
import typing
from pathlib import Path

HERE = Path(__file__).parent


class ListNode:
    def __init__(self, val=0, next=None):
        self.val, self.next = val, next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val, self.left, self.right = val, left, right


def load(slug):
    for d in ("solutions", "eval_solutions"):
        p = HERE / d / f"{slug}.py"
        if p.exists():
            ns = {**vars(typing), **vars(collections), "heapq": heapq, "math": math, "bisect_left": bisect.bisect_left,
                  "bisect_right": bisect.bisect_right, "ListNode": ListNode, "TreeNode": TreeNode}
            exec(compile(p.read_text(), str(p), "exec"), ns)
            return ns
    raise FileNotFoundError(slug)


def S(slug):
    return load(slug)["Solution"]()


def linked(vals, pos=-1):
    nodes = [ListNode(v) for v in vals]
    for a, b in zip(nodes, nodes[1:]):
        a.next = b
    if pos >= 0 and nodes:
        nodes[-1].next = nodes[pos]
    return (nodes[0] if nodes else None), nodes


def to_list(head):
    out = []
    while head:
        out.append(head.val)
        head = head.next
    return out


def tree(vals):
    if not vals:
        return None
    it = iter(vals)
    root = TreeNode(next(it))
    q = collections.deque([root])
    for v in it:
        node = q[0]
        child = TreeNode(v) if v is not None else None
        if node.left is None and not getattr(node, "_l", False):
            node.left, node._l = child, True
        else:
            node.right = child
            q.popleft()
        if child:
            q.append(child)
    return root


def find(root, val):
    if not root:
        return None
    if root.val == val:
        return root
    return find(root.left, val) or find(root.right, val)


def norm(xss):
    return sorted(sorted(x) for x in xss)


def test_library():
    assert sorted(S("two-sum").twoSum([2, 7, 11, 15], 9)) == [0, 1]
    assert sorted(S("two-sum").twoSum([3, 3], 6)) == [0, 1]
    assert S("container-with-most-water").maxArea([1, 8, 6, 2, 5, 4, 8, 3, 7]) == 49
    assert norm(S("3sum").threeSum([-1, 0, 1, 2, -1, -4])) == [[-1, -1, 2], [-1, 0, 1]]
    assert S("3sum").threeSum([0, 0, 0, 0]) == [[0, 0, 0]]
    f = S("longest-substring-without-repeating-characters").lengthOfLongestSubstring
    assert (f("abcabcbb"), f("bbbbb"), f("pwwkew"), f(""), f("abba")) == (3, 1, 3, 0, 2)
    f = S("minimum-window-substring").minWindow
    assert (f("ADOBECODEBANC", "ABC"), f("a", "a"), f("a", "aa")) == ("BANC", "a", "")
    assert S("binary-search").search([-1, 0, 3, 5, 9, 12], 9) == 4
    assert S("binary-search").search([-1, 0, 3, 5, 9, 12], 2) == -1
    f = S("search-in-rotated-sorted-array").search
    assert (f([4, 5, 6, 7, 0, 1, 2], 0), f([4, 5, 6, 7, 0, 1, 2], 3), f([1], 0), f([3, 1], 1)) == (4, -1, -1, 1)
    f = S("subarray-sum-equals-k").subarraySum
    assert (f([1, 1, 1], 2), f([1, 2, 3], 3), f([1, -1, 0], 0)) == (2, 2, 3)
    f = S("car-pooling").carPooling
    assert (f([[2, 1, 5], [3, 3, 7]], 4), f([[2, 1, 5], [3, 3, 7]], 5), f([[2, 1, 5], [3, 5, 7]], 3)) == (False, True, True)
    assert norm(S("group-anagrams").groupAnagrams(["eat", "tea", "tan", "ate", "nat", "bat"])) == norm([["bat"], ["nat", "tan"], ["ate", "eat", "tea"]])
    assert S("daily-temperatures").dailyTemperatures([73, 74, 75, 71, 69, 72, 76, 73]) == [1, 1, 4, 2, 1, 1, 0, 0]
    assert S("sliding-window-maximum").maxSlidingWindow([1, 3, -1, -3, 5, 3, 6, 7], 3) == [3, 3, 5, 5, 6, 7]
    assert S("kth-largest-element-in-an-array").findKthLargest([3, 2, 3, 1, 2, 4, 5, 5, 6], 4) == 4
    lists = [linked(v)[0] for v in ([1, 4, 5], [1, 3, 4], [2, 6])]
    assert to_list(S("merge-k-sorted-lists").mergeKLists(lists)) == [1, 1, 2, 3, 4, 4, 5, 6]
    assert S("merge-k-sorted-lists").mergeKLists([]) is None
    f = S("rotting-oranges").orangesRotting
    assert (f([[2, 1, 1], [1, 1, 0], [0, 1, 1]]), f([[2, 1, 1], [0, 1, 1], [1, 0, 1]]), f([[0, 2]])) == (4, -1, 0)
    assert len(S("permutations").permute([1, 2, 3])) == 6
    assert norm(S("permutations").permute([0, 1])) == [[0, 1], [0, 1]]
    assert norm(S("subsets").subsets([1, 2, 3])) == norm([[], [1], [2], [1, 2], [3], [1, 3], [2, 3], [1, 2, 3]])
    f = S("course-schedule").canFinish
    assert (f(2, [[1, 0]]), f(2, [[1, 0], [0, 1]])) == (True, False)
    f = S("number-of-provinces").findCircleNum
    assert (f([[1, 1, 0], [1, 1, 0], [0, 0, 1]]), f([[1, 0, 0], [0, 1, 0], [0, 0, 1]])) == (2, 3)
    f = S("network-delay-time").networkDelayTime
    assert (f([[2, 1, 1], [2, 3, 1], [3, 4, 1]], 4, 2), f([[1, 2, 1]], 2, 1), f([[1, 2, 1]], 2, 2)) == (2, 1, -1)
    f = S("climbing-stairs").climbStairs
    assert (f(1), f(2), f(3), f(5)) == (1, 2, 3, 8)
    f = S("longest-increasing-subsequence").lengthOfLIS
    assert (f([10, 9, 2, 5, 3, 7, 101, 18]), f([0, 1, 0, 3, 2, 3]), f([7, 7, 7])) == (4, 4, 1)
    f = S("longest-common-subsequence").longestCommonSubsequence
    assert (f("abcde", "ace"), f("abc", "def")) == (3, 0)
    f = S("longest-palindromic-subsequence").longestPalindromeSubseq
    assert (f("bbbab"), f("cbbd"), f("a")) == (4, 2, 1)
    f = S("coin-change").coinChange
    assert (f([1, 2, 5], 11), f([2], 3), f([1], 0)) == (3, -1, 0)
    f = S("jump-game").canJump
    assert (f([2, 3, 1, 1, 4]), f([3, 2, 1, 0, 4]), f([0])) == (True, False, True)
    assert S("merge-intervals").merge([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]
    assert S("merge-intervals").merge([[1, 4], [2, 3]]) == [[1, 4]]
    assert to_list(S("reverse-linked-list").reverseList(linked([1, 2, 3, 4, 5])[0])) == [5, 4, 3, 2, 1]
    assert S("linked-list-cycle").hasCycle(linked([3, 2, 0, -4], 1)[0]) is True
    assert S("linked-list-cycle").hasCycle(linked([1])[0]) is False
    assert S("binary-tree-level-order-traversal").levelOrder(tree([3, 9, 20, None, None, 15, 7])) == [[3], [9, 20], [15, 7]]
    f = S("validate-binary-search-tree").isValidBST
    assert (f(tree([2, 1, 3])), f(tree([5, 1, 4, None, None, 3, 6])), f(tree([5, 4, 6, None, None, 3, 7]))) == (True, False, False)
    t = load("implement-trie-prefix-tree")["Trie"]()
    t.insert("apple")
    assert (t.search("apple"), t.search("app"), t.startsWith("app")) == (True, False, True)
    t.insert("app")
    assert t.search("app") is True
    na = load("range-sum-query-mutable")["NumArray"]([1, 3, 5])
    assert na.sumRange(0, 2) == 9
    na.update(1, 2)
    assert na.sumRange(0, 2) == 8 and na.sumRange(1, 1) == 2
    assert S("single-number").singleNumber([4, 1, 2, 1, 2]) == 4
    c = load("lru-cache")["LRUCache"](2)
    c.put(1, 1); c.put(2, 2)
    assert c.get(1) == 1
    c.put(3, 3)
    assert c.get(2) == -1
    c.put(4, 4)
    assert (c.get(1), c.get(3), c.get(4)) == (-1, 3, 4)


def test_eval():
    assert S("two-sum-ii-input-array-is-sorted").twoSum([2, 7, 11, 15], 9) == [1, 2]
    f = S("trapping-rain-water").trap
    assert (f([0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1]), f([4, 2, 0, 3, 2, 5]), f([])) == (6, 9, 0)
    f = S("find-all-anagrams-in-a-string").findAnagrams
    assert (f("cbaebabacd", "abc"), f("abab", "ab"), f("a", "ab")) == ([0, 6], [0, 1, 2], [])
    f = S("longest-repeating-character-replacement").characterReplacement
    assert (f("ABAB", 2), f("AABABBA", 1)) == (4, 4)
    f = S("find-minimum-in-rotated-sorted-array").findMin
    assert (f([3, 4, 5, 1, 2]), f([4, 5, 6, 7, 0, 1, 2]), f([11, 13, 15, 17]), f([2, 1])) == (1, 0, 11, 1)
    f = S("koko-eating-bananas").minEatingSpeed
    assert (f([3, 6, 7, 11], 8), f([30, 11, 23, 4, 20], 5), f([30, 11, 23, 4, 20], 6)) == (4, 30, 23)
    f = S("subarray-sums-divisible-by-k").subarraysDivByK
    assert (f([4, 5, 0, -2, -3, 1], 5), f([5], 9), f([-1, 2, 9], 2)) == (7, 0, 2)
    f = S("largest-rectangle-in-histogram").largestRectangleArea
    assert (f([2, 1, 5, 6, 2, 3]), f([2, 4]), f([1, 1])) == (10, 4, 2)
    assert S("next-greater-element-i").nextGreaterElement([4, 1, 2], [1, 3, 4, 2]) == [-1, 3, -1]
    assert sorted(S("top-k-frequent-elements").topKFrequent([1, 1, 1, 2, 2, 3], 2)) == [1, 2]
    f = S("course-schedule-ii").findOrder
    order = f(4, [[1, 0], [2, 0], [3, 1], [3, 2]])
    assert order[0] == 0 and order[-1] == 3 and len(order) == 4
    assert f(2, [[1, 0], [0, 1]]) == []
    f = S("redundant-connection").findRedundantConnection
    assert (f([[1, 2], [1, 3], [2, 3]]), f([[1, 2], [2, 3], [3, 4], [1, 4], [1, 5]])) == ([2, 3], [1, 4])
    f = S("shortest-path-in-binary-matrix").shortestPathBinaryMatrix
    assert (f([[0, 1], [1, 0]]), f([[0, 0, 0], [1, 1, 0], [1, 1, 0]]), f([[1, 0, 0], [1, 1, 0], [1, 1, 0]])) == (2, 4, -1)
    assert norm(S("combination-sum").combinationSum([2, 3, 6, 7], 7)) == [[2, 2, 3], [7]]
    assert S("combination-sum").combinationSum([2], 1) == []
    f = S("house-robber").rob
    assert (f([1, 2, 3, 1]), f([2, 7, 9, 3, 1]), f([2, 1, 1, 2])) == (4, 12, 4)
    f = S("partition-equal-subset-sum").canPartition
    assert (f([1, 5, 11, 5]), f([1, 2, 3, 5])) == (True, False)
    f = S("non-overlapping-intervals").eraseOverlapIntervals
    assert (f([[1, 2], [2, 3], [3, 4], [1, 3]]), f([[1, 2], [1, 2], [1, 2]]), f([[1, 2], [2, 3]])) == (1, 2, 0)
    head, nodes = linked([3, 2, 0, -4], 1)
    assert S("linked-list-cycle-ii").detectCycle(head) is nodes[1]
    assert S("linked-list-cycle-ii").detectCycle(linked([1])[0]) is None
    root = tree([3, 5, 1, 6, 2, 0, 8, None, None, 7, 4])
    f = S("lowest-common-ancestor-of-a-binary-tree").lowestCommonAncestor
    assert f(root, find(root, 5), find(root, 1)).val == 3
    assert f(root, find(root, 5), find(root, 4)).val == 5
    f = S("number-of-1-bits").hammingWeight
    assert (f(11), f(128), f(2147483645)) == (3, 1, 30)


if __name__ == "__main__":
    failed = 0
    for name, fn in [("library", test_library), ("eval", test_eval)]:
        try:
            fn()
            print(f"[ok] {name}")
        except AssertionError:
            failed += 1
            import traceback
            traceback.print_exc()
    sys.exit(1 if failed else 0)
