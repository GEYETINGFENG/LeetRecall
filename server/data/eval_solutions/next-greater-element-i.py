class Solution:
    def nextGreaterElement(self, nums1: List[int], nums2: List[int]) -> List[int]:
        nxt = {}
        st = []
        for x in nums2:
            while st and st[-1] < x:
                nxt[st.pop()] = x
            st.append(x)
        return [nxt.get(x, -1) for x in nums1]
