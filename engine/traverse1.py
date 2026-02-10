class Traverse:
    def __init__(self, x1, y1, x2, y2, snap_distance=40, name="Traverse"):
        self.name = name
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.snap_distance = snap_distance
        self.snap_points = []

        self.generate_snap_points()

    def generate_snap_points(self):
        self.snap_points.clear()

        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        length = (dx**2 + dy**2) ** 0.5
        steps = max(1, int(length // self.snap_distance))

        for i in range(steps + 1):
            t = i / steps
            self.snap_points.append({
                "x": self.x1 + dx * t,
                "y": self.y1 + dy * t,
                "occupied": False,
                "fixture": None,
            })