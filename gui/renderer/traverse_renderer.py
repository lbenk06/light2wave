import numpy as np
from nicegui import ui

def draw_traverses(parent_element, traverses, scale=1.0):
    """
    Zeichnet Traverses in das übergebene Parent-Element.
    """

    parent_element.clear()

    content = ""

    for t in traverses:

        d = t.snap_distance * scale / 2
        dx = t.x2* scale - t.x1 * scale
        dy = t.y2 * scale - t.y1 * scale

        nx, ny = -dy, dx
        length = (nx**2 + ny**2) ** 0.5
        nx, ny = nx / length, ny / length

        dx_n, dy_n = nx * d, ny * d

        Ax, Ay = t.x1 * scale + dx_n, t.y1 * scale + dy_n
        Bx, By = t.x2 * scale + dx_n, t.y2 * scale + dy_n
        Cx, Cy = t.x2 * scale - dx_n, t.y2 * scale - dy_n
        Dx, Dy = t.x1 * scale - dx_n, t.y1 * scale - dy_n

        # Rahmen
        w = 6 * scale  # Breite der Traverse
        content += f'''
        <line x1="{Ax}" y1="{Ay}" x2="{Bx}" y2="{By}" stroke="grey" stroke-width="{w}"/>
        <line x1="{Bx}" y1="{By}" x2="{Cx}" y2="{Cy}" stroke="grey" stroke-width="{w}"/>
        <line x1="{Cx}" y1="{Cy}" x2="{Dx}" y2="{Dy}" stroke="grey" stroke-width="{w}"/>
        <line x1="{Dx}" y1="{Dy}" x2="{Ax}" y2="{Ay}" stroke="grey" stroke-width="{w}"/>
        '''

        corner_radius = 4 * scale  # Radius des Kreises

        for (x, y) in [(Ax, Ay), (Bx, By), (Cx, Cy), (Dx, Dy)]:
            content += f'<circle cx="{x}" cy="{y}" r="{corner_radius}" fill="gray"/>'

        # Obere Kante: Ax -> Bx
        vec_top = (Bx - Ax, By - Ay)

        # Untere Kante: Dx -> Cx
        vec_bottom = (Cx - Dx, Cy - Dy)

        len_top = np.sqrt(vec_top[0]**2 + vec_top[1]**2)
        ux_top, uy_top = vec_top[0]/len_top, vec_top[1]/len_top

        len_bottom = np.sqrt(vec_bottom[0]**2 + vec_bottom[1]**2)
        ux_bottom, uy_bottom = vec_bottom[0]/len_bottom, vec_bottom[1]/len_bottom

        # Diagonalen
        num_steps = max(1, int(len_top // (t.snap_distance * scale)))

        for i in range(num_steps):
            t1 = i * t.snap_distance * scale / len_top
            t2 = (i + 1) * t.snap_distance * scale / len_top

            x_top_start = Ax + (Bx - Ax) * t1
            y_top_start = Ay + (By - Ay) * t1
            x_top_end = Ax + (Bx - Ax) * t2
            y_top_end = Ay + (By - Ay) * t2

            x_bottom_start = Dx + (Cx - Dx) * t1
            y_bottom_start = Dy + (Cy - Dy) * t1
            x_bottom_end = Dx + (Cx - Dx) * t2
            y_bottom_end = Dy + (Cy - Dy) * t2

            b = 4 * scale  # Breite der Diagonalen
            content += f'<line x1="{x_top_start}" y1="{y_top_start}" x2="{x_bottom_end}" y2="{y_bottom_end}" stroke="grey" stroke-width="{b}"/>'
            content += f'<line x1="{x_bottom_start}" y1="{y_bottom_start}" x2="{x_top_end}" y2="{y_top_end}" stroke="grey" stroke-width="{b}"/>'

    with parent_element:
        ui.html(f'''
        <svg width="100%" height="100%" 
             style="position:absolute; top:0; left:0; pointer-events:none;">
            {content}
        </svg>
        ''', sanitize=False)