class Solution:
    def largestRectangleArea(self, heights: List[int]) -> int:
        st = []
        best = 0
        hs = heights + [0]
        for i, h in enumerate(hs):
            while st and hs[st[-1]] >= h:
                top = st.pop()
                width = i if not st else i - st[-1] - 1
                best = max(best, hs[top] * width)
            st.append(i)
        return best
