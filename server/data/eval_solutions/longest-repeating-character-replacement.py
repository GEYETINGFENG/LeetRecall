class Solution:
    def characterReplacement(self, s: str, k: int) -> int:
        cnt = defaultdict(int)
        left = 0
        maxf = 0
        for right, ch in enumerate(s):
            cnt[ch] += 1
            maxf = max(maxf, cnt[ch])
            if right - left + 1 - maxf > k:
                cnt[s[left]] -= 1
                left += 1
        return len(s) - left
