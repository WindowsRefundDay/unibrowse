import os
import sys
from PySide6.QtGui import QPainter, QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize, Qt

def render_svg(svg_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    renderer = QSvgRenderer(svg_path)
    
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for size in sizes:
        # Standard resolution
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
        img.save(os.path.join(output_dir, f"icon_{size}x{size}.png"))
        
        # High resolution (@2x)
        if size <= 512:
            img2x = QImage(size*2, size*2, QImage.Format_ARGB32)
            img2x.fill(Qt.transparent)
            painter2x = QPainter(img2x)
            renderer.render(painter2x)
            painter2x.end()
            img2x.save(os.path.join(output_dir, f"icon_{size}x{size}@2x.png"))

if __name__ == "__main__":
    svg_path = sys.argv[1]
    output_dir = sys.argv[2]
    render_svg(svg_path, output_dir)
