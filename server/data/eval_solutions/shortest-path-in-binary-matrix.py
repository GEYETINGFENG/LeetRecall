class Solution:
    def shortestPathBinaryMatrix(self, grid: List[List[int]]) -> int:
        n = len(grid)
        if grid[0][0] or grid[n - 1][n - 1]:
            return -1
        q = deque([(0, 0, 1)])
        grid[0][0] = 1
        while q:
            i, j, d = q.popleft()
            if i == n - 1 and j == n - 1:
                return d
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    x, y = i + di, j + dj
                    if 0 <= x < n and 0 <= y < n and grid[x][y] == 0:
                        grid[x][y] = 1
                        q.append((x, y, d + 1))
        return -1
