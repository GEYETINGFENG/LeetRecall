class Solution:
    def subsets(self, nums: List[int]) -> List[List[int]]:
        res, path = [], []

        def dfs(i):
            if i == len(nums):
                res.append(path[:])
                return
            dfs(i + 1)          # skip nums[i]
            path.append(nums[i])
            dfs(i + 1)          # take nums[i]
            path.pop()

        dfs(0)
        return res
