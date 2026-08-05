"""
Camera preview system. It's all smoke and mirros :)
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

CHARACTER_HEIGHT = 180.0
NEAR = 1.0

INK = QColor(210, 214, 220)
DIM = QColor(120, 126, 136)
GRID = QColor(70, 74, 82)
PATH = QColor(120, 190, 255)
AIM = QColor(255, 170, 90)
FRUST = QColor(255, 235, 130)
BODY = QColor(150, 220, 160)
WARN = QColor(255, 110, 110)


def reference_figure():
    # Reference figure drawn by lines, Ryu sized, will be out of frame for cameas built for Dorm/Sentinel/etc.
    h = CHARACTER_HEIGHT
    hip, chest, neck, top = 0.52 * h, 0.72 * h, 0.82 * h, h
    shoulder, hand, foot = 0.20 * h, 0.28 * h, 0.11 * h
    seg = [
        ((0, hip, 0), (0, neck, 0)),                       # spine
        ((-shoulder, chest, 0), (shoulder, chest, 0)),     # shoulders
        ((-shoulder, chest, 0), (-hand, hip * 1.05, 0)),   # arms
        ((shoulder, chest, 0), (hand, hip * 1.05, 0)),
        ((0, hip, 0), (-foot, 0, 0)),                      # legs
        ((0, hip, 0), (foot, 0, 0)),
    ]
    r, cy = 0.09 * h, (neck + top) / 2.0
    prev = None
    for i in range(13):
        a = i / 12.0 * math.tau
        p = (r * math.sin(a), cy + r * math.cos(a), 0.0)
        if prev:
            seg.append((prev, p))
        prev = p
    return seg


def ground_grid(extent=400.0, step=100.0):
    seg = []
    n = int(extent / step)
    for i in range(-n, n + 1):
        d = i * step
        seg.append(((d, 0.0, -extent), (d, 0.0, extent)))
        seg.append(((-extent, 0.0, d), (extent, 0.0, d)))
    return seg


def quat_rotate(q, v):
    x, y, z, w = q
    t = (2 * (y * v[2] - z * v[1]),
         2 * (z * v[0] - x * v[2]),
         2 * (x * v[1] - y * v[0]))
    c = (y * t[2] - z * t[1], z * t[0] - x * t[2], x * t[1] - y * t[0])
    return tuple(v[i] + w * t[i] + c[i] for i in range(3))


class CameraPreview(QWidget):
    """Draws one camera at one frame."""

    def __init__(self, mode="scene"):
        super().__init__()
        self.mode = mode
        self.cam = None
        self.frame = 0
        self.view = "front"
        self.setMinimumSize(240, 200)
        self._figure = reference_figure()
        self._grid = ground_grid()

    def set_camera(self, cam):
        self.cam = cam
        self.frame = 0
        self.update()

    def set_frame(self, f):
        self.frame = f
        self.update()

    def set_view(self, name):
        self.view = name
        self.update()

    # ------------------------------------------------------------ painting

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(34, 36, 40))
        if not self.cam or self.cam.frames == 0:
            p.setPen(DIM)
            p.drawText(self.rect(), Qt.AlignCenter, "No camera selected")
            return
        f = max(0, min(self.frame, self.cam.frames - 1))
        if self.mode == "scene":
            self._paint_scene(p, f)
        else:
            self._paint_lens(p, f)

    # ------------------------------------------------------------- outside

    def _project_ortho(self, pt, scale, cx, cy):
        if self.view == "front":     # looking down -Z
            u, v = pt[0], pt[1]
        elif self.view == "side":    # looking down -X
            u, v = pt[2], pt[1]
        else:                        # top, looking down -Y
            u, v = pt[0], -pt[2]
        return QPointF(cx + u * scale, cy - v * scale)

    def _paint_scene(self, p, f):
        cam = self.cam
        pts = [cam.eye[f], cam.target[f], (0.0, 0.0, 0.0),
               (0.0, CHARACTER_HEIGHT, 0.0)]
        pts += list(cam.eye)
        lo = [min(q[i] for q in pts) for i in range(3)]
        hi = [max(q[i] for q in pts) for i in range(3)]
        span = max(hi[i] - lo[i] for i in range(3)) or 1.0
        span = max(span, CHARACTER_HEIGHT * 1.4)
        mid = [(hi[i] + lo[i]) / 2.0 for i in range(3)]

        w, h = self.width(), self.height()
        scale = 0.78 * min(w, h) / span
        base = self._project_ortho(mid, scale, 0, 0)
        cx, cy = w / 2.0 - base.x(), h / 2.0 - base.y()

        def to(pt):
            return self._project_ortho(pt, scale, cx, cy)

        p.setPen(QPen(GRID, 1))
        for a, b in self._grid:
            p.drawLine(to(a), to(b))

        p.setPen(QPen(BODY, 2))
        for a, b in self._figure:
            p.drawLine(to(a), to(b))

        p.setPen(QPen(PATH, 1))
        poly = QPolygonF([to(e) for e in cam.eye])
        p.drawPolyline(poly)

        p.setPen(QPen(AIM, 1, Qt.DotLine))
        p.drawLine(to(cam.eye[f]), to(cam.target[f]))

        # four corner rays out to the aim distance
        eye, q = cam.eye[f], cam.rot[f]
        fwd = quat_rotate(q, (0.0, 0.0, -1.0))
        right = quat_rotate(q, (1.0, 0.0, 0.0))
        up = quat_rotate(q, (0.0, 1.0, 0.0))
        dist = math.dist(eye, cam.target[f]) or 100.0
        ty = math.tan(math.radians(cam.fov[f]) / 2.0)
        tx = ty * 16.0 / 9.0
        p.setPen(QPen(FRUST, 1))
        corners = []
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            c = tuple(eye[i] + (fwd[i] + right[i] * sx * tx + up[i] * sy * ty) * dist
                      for i in range(3))
            corners.append(c)
            p.drawLine(to(eye), to(c))
        p.drawPolygon(QPolygonF([to(c) for c in corners]))

        p.setPen(QPen(INK, 1))
        p.setFont(QFont(self.font().family(), 8))
        p.drawText(8, 16, "%s view" % self.view)
        p.drawText(8, h - 8, "eye %.0f %.0f %.0f   %.0f units out"
                   % (eye[0], eye[1], eye[2], dist))

    # -------------------------------------------------------- through lens

    def _paint_lens(self, p, f):
        cam = self.cam
        eye, q = cam.eye[f], cam.rot[f]
        fwd = quat_rotate(q, (0.0, 0.0, -1.0))
        right = quat_rotate(q, (1.0, 0.0, 0.0))
        up = quat_rotate(q, (0.0, 1.0, 0.0))
        ty = math.tan(math.radians(max(cam.fov[f], 0.5)) / 2.0)

        w, h = self.width(), self.height()
        # a 16:9 frame centred in whatever space the widget has
        fw = min(w - 16, (h - 16) * 16.0 / 9.0)
        fh = fw * 9.0 / 16.0
        frame = QRectF((w - fw) / 2.0, (h - fh) / 2.0, fw, fh)
        p.fillRect(frame, QColor(24, 26, 30))

        tx = ty * 16.0 / 9.0

        def view_space(pt):
            d = [pt[i] - eye[i] for i in range(3)]
            return (sum(d[i] * right[i] for i in range(3)),
                    sum(d[i] * up[i] for i in range(3)),
                    sum(d[i] * fwd[i] for i in range(3)))

        def to_screen(v):
            sx = (v[0] / v[2]) / tx
            sy = (v[1] / v[2]) / ty
            return QPointF(frame.center().x() + sx * fw / 2.0,
                           frame.center().y() - sy * fh / 2.0)

        def draw(seg, pen):
            p.setPen(pen)
            for a, b in seg:
                va, vb = view_space(a), view_space(b)
                if va[2] <= NEAR and vb[2] <= NEAR:
                    continue
                if va[2] <= NEAR or vb[2] <= NEAR:
                    # clip the crossing end back to the near plane
                    t = (NEAR - va[2]) / (vb[2] - va[2])
                    mid = tuple(va[i] + (vb[i] - va[i]) * t for i in range(3))
                    if va[2] <= NEAR:
                        va = mid
                    else:
                        vb = mid
                p.drawLine(to_screen(va), to_screen(vb))

        p.setClipRect(frame)
        draw(self._grid, QPen(GRID, 1))
        draw(self._figure, QPen(BODY, 2))
        p.setClipping(False)

        # is the character actually in shot?
        inside = False
        for a, b in self._figure:
            for pt in (a, b):
                v = view_space(pt)
                if v[2] <= NEAR:
                    continue
                if abs((v[0] / v[2]) / tx) <= 1.0 and abs((v[1] / v[2]) / ty) <= 1.0:
                    inside = True
                    break
            if inside:
                break

        p.setPen(QPen(DIM if inside else WARN, 1))
        p.drawRect(frame)
        p.setFont(QFont(self.font().family(), 8))
        p.drawText(int(frame.left()), int(frame.top()) - 4,
                   "frame %d   fov %.1f  roll %.1f deg"
                   % (f, cam.fov[f], math.degrees(cam.roll[f])))
        if not inside:
            p.setPen(WARN)
            p.drawText(frame, Qt.AlignBottom | Qt.AlignHCenter,
                       "character is out of shot")


class PreviewPanel(QWidget):
    # The whole ass preview panel. Has top, bottom, and two side-by-side views. Also has a timeline scrubber and play/pause button.

    frameChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.cam = None

        self.scene = CameraPreview("scene")
        self.lens = CameraPreview("lens")

        self.view_pick = QComboBox()
        self.view_pick.addItems(["front", "side", "top"])
        self.view_pick.currentTextChanged.connect(self.scene.set_view)

        self.play = QPushButton("Play")
        self.play.setCheckable(True)
        self.play.toggled.connect(self._toggle)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._scrub)

        self.readout = QLabel("")
        self.readout.setMinimumWidth(120)

        self.timer = QTimer(self)
        self.timer.setInterval(1000 // 60)
        self.timer.timeout.connect(self._tick)

        views = QHBoxLayout()
        views.addWidget(self.scene, 1)
        views.addWidget(self.lens, 1)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("View"))
        bar.addWidget(self.view_pick)
        bar.addWidget(self.play)
        bar.addWidget(self.slider, 1)
        bar.addWidget(self.readout)

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addLayout(views, 1)
        box.addLayout(bar)

    def set_camera(self, cam):
        self.cam = cam
        self.play.setChecked(False)
        self.scene.set_camera(cam)
        self.lens.set_camera(cam)
        n = cam.frames if cam else 0
        self.slider.setEnabled(n > 1)
        self.slider.setRange(0, max(0, n - 1))
        self.slider.setValue(0)
        self._scrub(0)

    def _scrub(self, value):
        self.scene.set_frame(value)
        self.lens.set_frame(value)
        if self.cam:
            self.readout.setText("frame %d / %d" % (value, self.cam.frames - 1))
        else:
            self.readout.setText("")
        self.frameChanged.emit(value)

    def _toggle(self, on):
        self.play.setText("Pause" if on else "Play")
        if on and self.cam and self.cam.frames > 1:
            self.timer.start()
        else:
            self.timer.stop()

    def _tick(self):
        if not self.cam:
            return
        nxt = self.slider.value() + 1
        self.slider.setValue(0 if nxt > self.slider.maximum() else nxt)
