import numpy as np

class Traverse:
    def __init__(self, x1, y1, x2, y2, snap_distance=50, name="Traverse"):
        self.name = name
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.snap_distance = snap_distance
        self.snap_points = []

        self.generate_snap_points()

    def generate_snap_points(self):
        self.snap_points.clear()

        # Richtungsvektor
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        length = (dx**2 + dy**2) ** 0.5
        steps = max(1, int(length // self.snap_distance))

        vx, vy = self.x2 - self.x1, self.y2 - self.y1

        # Normalvektor
        nx, ny = -vy, vx
        norm = np.sqrt(nx**2 + ny**2)
        nx, ny = nx / norm, ny / norm

        # Verschoben
        d = self.snap_distance / 2 + 15
        dx_n, dy_n = nx * d, ny * d

        # Eckpunkte
        Ax, Ay = self.x1 + dx_n, self.y1 + dy_n
        Bx, By = self.x2 + dx_n, self.y2 + dy_n
        Cx, Cy = self.x1 - dx_n, self.y1 - dy_n
        Dx, Dy = self.x2 - dx_n, self.y2 - dy_n

        for i in range(steps + 1):
            t = i / steps
            self.snap_points.append({
                "x": Ax + (Bx - Ax) * t,
                "y": Ay + (By - Ay) * t,
                "occupied": False,
                "fixture": None,
            })

        for i in range(steps + 1):
            t = i / steps
            self.snap_points.append({
                "x": Cx + (Dx - Cx) * t,
                "y": Cy + (Dy - Cy) * t,
                "occupied": False,
                "fixture": None,
            })