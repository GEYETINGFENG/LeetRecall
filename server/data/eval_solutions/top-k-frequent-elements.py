class Solution:
    def topKFrequent(self, nums: List[int], k: int) -> List[int]:
        cnt = Counter(nums)
        heap = []
        for x, c in cnt.items():
            heapq.heappush(heap, (c, x))
            if len(heap) > k:
                heapq.heappop(heap)
        return [x for _, x in heap]
