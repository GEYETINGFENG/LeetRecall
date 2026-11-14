class Solution:
    def findAnagrams(self, s: str, p: str) -> List[int]:
        k = len(p)
        if len(s) < k:
            return []
        need = [0] * 26
        win = [0] * 26
        for ch in p:
            need[ord(ch) - 97] += 1
        res = []
        for i, ch in enumerate(s):
            win[ord(ch) - 97] += 1
            if i >= k:
                win[ord(s[i - k]) - 97] -= 1
            if i >= k - 1 and win == need:
                res.append(i - k + 1)
        return res
