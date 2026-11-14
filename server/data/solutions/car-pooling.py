class Solution:
    def carPooling(self, trips: List[List[int]], capacity: int) -> bool:
        diff = [0] * 1002
        for num, frm, to in trips:
            diff[frm] += num
            diff[to] -= num  # passengers get off at `to`
        cur = 0
        for d in diff:
            cur += d
            if cur > capacity:
                return False
        return True
