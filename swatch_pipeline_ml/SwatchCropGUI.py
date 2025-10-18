import sys
import os
import json
from PyQt5 import QtWidgets, QtGui, QtCore
from PIL import Image
from PIL.ImageQt import ImageQt

INPUT_DIR = "inputs/ghosts"
OUTPUT_DIR = "outputs/swatches"
LOG_PATH = "logs/swatch_hints.json"
CROP_SIZE = 300

GARMENT_TYPES = ["default", "dresses", "pants", "tops", "sweater", "coat"]


class ImageLabel(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.crop_rect = QtCore.QRect(100, 100, CROP_SIZE, CROP_SIZE)
        self.dragging = False
        self.drag_offset = QtCore.QPoint()
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.crop_rect.contains(event.pos()):
            self.dragging = True
            self.drag_offset = event.pos() - self.crop_rect.topLeft()

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_top_left = event.pos() - self.drag_offset
            self.crop_rect.moveTo(new_top_left)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False

    def keyPressEvent(self, event):
        step = 10
        if event.key() == QtCore.Qt.Key_Left:
            self.crop_rect.translate(-step, 0)
        elif event.key() == QtCore.Qt.Key_Right:
            self.crop_rect.translate(step, 0)
        elif event.key() == QtCore.Qt.Key_Up:
            self.crop_rect.translate(0, -step)
        elif event.key() == QtCore.Qt.Key_Down:
            self.crop_rect.translate(0, step)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtCore.Qt.red, 2, QtCore.Qt.SolidLine))
        painter.drawRect(self.crop_rect)


class SwatchCropper(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Swatch Cropper")
        self.setGeometry(100, 100, 1200, 800)
        self.image_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        self.current_index = 0
        self.garment_type = GARMENT_TYPES[0]
        self.pil_image = None

        self.initUI()
        self.loadImage()

    def initUI(self):
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        self.image_label = ImageLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignTop)

        self.garment_selector = QtWidgets.QComboBox()
        self.garment_selector.addItems(GARMENT_TYPES)
        self.garment_selector.currentIndexChanged.connect(self.setGarmentType)

        save_button = QtWidgets.QPushButton("Save Swatch")
        save_button.clicked.connect(self.saveSwatch)

        next_button = QtWidgets.QPushButton("Next Image")
        next_button.clicked.connect(self.nextImage)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.image_label)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.garment_selector)
        hbox.addWidget(save_button)
        hbox.addWidget(next_button)
        vbox.addLayout(hbox)

        self.central_widget.setLayout(vbox)

    def setGarmentType(self, index):
        self.garment_type = GARMENT_TYPES[index]

    def loadImage(self):
        if self.current_index >= len(self.image_files):
            QtWidgets.QMessageBox.information(self, "Done", "All images processed!")
            return

        image_path = os.path.join(INPUT_DIR, self.image_files[self.current_index])
        self.pil_image = Image.open(image_path).convert("RGB")
        qt_image = ImageQt(self.pil_image)
        pixmap = QtGui.QPixmap.fromImage(qt_image)
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(pixmap.size())

    def saveSwatch(self):
        if self.pil_image is None:
            return

        img = self.pil_image
        left = self.image_label.crop_rect.x()
        upper = self.image_label.crop_rect.y()
        right = left + CROP_SIZE
        lower = upper + CROP_SIZE

        cropped = img.crop((left, upper, right, lower))
        original_filename = self.image_files[self.current_index]
        swatch_filename = original_filename.replace("_ghost", "").split(".")[0] + "_swatch.jpg"
        output_path = os.path.join(OUTPUT_DIR, swatch_filename)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cropped.save(output_path)

        # Build log entry with garment type and crop coordinates
        log_entry = {
            "filename": original_filename,
            "swatch": swatch_filename,
            "garment_type": self.garment_type,
            "crop": {
                "x": left,
                "y": upper,
                "width": CROP_SIZE,
                "height": CROP_SIZE
            }
        }

        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []
        else:
            data = []

        data.append(log_entry)

        with open(LOG_PATH, "w") as f:
            json.dump(data, f, indent=2)

        QtWidgets.QMessageBox.information(
            self,
            "Saved",
            f"Swatch saved as {swatch_filename}\nGarment type: {self.garment_type}"
        )

    def nextImage(self):
        self.current_index += 1
        self.loadImage()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = SwatchCropper()
    win.show()
    sys.exit(app.exec_())
