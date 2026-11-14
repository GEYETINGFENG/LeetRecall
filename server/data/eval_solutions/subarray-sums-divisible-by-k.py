class Solution:
    def subarraysDivByK(self, nums: List[int], k: int) -> int:
        cnt = [0] * k
        cnt[0] = 1
        pre = 0
        ans = 0
        for x in nums:
            pre = (pre + x) % k
            ans += cnt[pre]
            cnt[pre] += 1
        return ans
