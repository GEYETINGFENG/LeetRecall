class Solution:
    def subarraySum(self, nums: List[int], k: int) -> int:
        cnt = defaultdict(int)
        cnt[0] = 1
        pre = 0
        ans = 0
        for x in nums:
            pre += x
            ans += cnt[pre - k]
            cnt[pre] += 1
        return ans
