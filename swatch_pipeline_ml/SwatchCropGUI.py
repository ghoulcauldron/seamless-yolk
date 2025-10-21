import sys
import os
import json
from PyQt5 import QtWidgets, QtGui, QtCore
from PIL import Image

INPUT_DIR = "inputs/ghosts"
OUTPUT_DIR = "outputs/swatches"
LOG_PATH = "logs/swatch_hints.json"
CONFIG_PATH = "config/garment_config.json"
CROP_SIZE = 300 # Default size
MIN_CROP_SIZE = 50 # Minimum resize dimension


class ImageLabel(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.crop_rect = QtCore.QRect(100, 100, CROP_SIZE, CROP_SIZE)
        self.dragging = False
        self.drag_offset = QtCore.QPoint()
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.preview_mode = False

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self.crop_rect.contains(event.pos()):
                self.dragging = True
                self.drag_offset = event.pos() - self.crop_rect.topLeft()
            else:
                new_top_left = event.pos() - QtCore.QPoint(
                    self.crop_rect.width() // 2, 
                    self.crop_rect.height() // 2
                )
                self.crop_rect.moveTo(new_top_left)
                self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            new_top_left = event.pos() - self.drag_offset
            self.crop_rect.moveTo(new_top_left)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False
    
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.preview_mode:
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
        self.pil_image = None
        self.original_pixmap = None
        
        # --- FIX: Add variables to store scroll position ---
        self.last_scroll_h = 0
        self.last_scroll_v = 0
        # --- END FIX ---

        self.garment_config = {}
        self.garment_types = ["default"]
        try:
            with open(CONFIG_PATH, 'r') as f:
                self.garment_config = json.load(f).get("garments", {})
                self.garment_types = ["default"] + [k for k in self.garment_config if k != "default"]
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load garment config. Using default. Error: {e}")
        
        self.garment_type = self.garment_types[0]
        
        self.initUI()
        self.loadImage()

    def initUI(self):
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setFocus()

        self.image_label = ImageLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignTop)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        
        self.garment_selector = QtWidgets.QComboBox()
        self.garment_selector.addItems(self.garment_types)
        self.garment_selector.currentIndexChanged.connect(self.setGarmentType)
        self.garment_selector.setFocusPolicy(QtCore.Qt.NoFocus) 
        
        add_type_button = QtWidgets.QPushButton("Add Type")
        add_type_button.clicked.connect(self.addNewGarmentType)
        add_type_button.setFocusPolicy(QtCore.Qt.NoFocus)

        save_button = QtWidgets.QPushButton("Save Swatch")
        save_button.clicked.connect(self.saveSwatch)
        save_button.setFocusPolicy(QtCore.Qt.NoFocus)

        next_button = QtWidgets.QPushButton("Next Image")
        next_button.clicked.connect(self.nextImage)
        next_button.setFocusPolicy(QtCore.Qt.NoFocus)
        
        prev_button = QtWidgets.QPushButton("Previous Image")
        prev_button.clicked.connect(self.prevImage)
        prev_button.setFocusPolicy(QtCore.Qt.NoFocus)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.scroll_area)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(prev_button)
        hbox.addWidget(next_button)
        hbox.addStretch(1)
        hbox.addWidget(QtWidgets.QLabel("Garment Type:"))
        hbox.addWidget(self.garment_selector)
        hbox.addWidget(add_type_button)
        hbox.addWidget(save_button)
        vbox.addLayout(hbox)

        self.central_widget.setLayout(vbox)

    def setGarmentType(self, index):
        self.garment_type = self.garment_types[index]

    def updateCropHint(self):
        if not self.pil_image or not self.garment_config: return
            
        hint = self.garment_config.get(self.garment_type, self.garment_config.get("default", {})).get("default_hint", {})
        left_ratio = hint.get("left_ratio", 0.35)
        top_ratio = hint.get("top_ratio", 0.35)

        img_width, img_height = self.pil_image.size
        
        self.image_label.crop_rect.setSize(QtCore.QSize(CROP_SIZE, CROP_SIZE))
        new_x = max(0, min(int(img_width * left_ratio), img_width - CROP_SIZE))
        new_y = max(0, min(int(img_height * top_ratio), img_height - CROP_SIZE))
        
        self.image_label.crop_rect.moveTo(new_x, new_y)
        self.image_label.update()

    def loadImage(self):
        if not (0 <= self.current_index < len(self.image_files)):
             QtWidgets.QMessageBox.information(self, "Info", "No more images.")
             self.current_index = max(0, min(self.current_index, len(self.image_files) - 1))
             return

        image_path = os.path.join(INPUT_DIR, self.image_files[self.current_index])
        self.pil_image = Image.open(image_path).convert("RGB")
        
        self.setWindowTitle(f"Swatch Cropper - {self.image_files[self.current_index]}")
        
        img = self.pil_image
        data = img.tobytes("raw", "RGB")
        qimage = QtGui.QImage(data, img.width, img.height, img.width * 3, QtGui.QImage.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        
        self.original_pixmap = pixmap
        self.image_label.setPixmap(self.original_pixmap)
        self.image_label.setFixedSize(self.original_pixmap.size())
        
        self.updateCropHint()
        self.setFocus()

    def saveSwatch(self):
        if self.pil_image is None: return

        rect = self.image_label.crop_rect
        cropped = self.pil_image.crop((rect.x(), rect.y(), rect.right(), rect.bottom()))
        
        original_filename = self.image_files[self.current_index]
        base_name = original_filename.split("_ghost")[0]
        swatch_filename = f"{base_name}_swatch.jpg"
        
        output_path = os.path.join(OUTPUT_DIR, swatch_filename)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        cropped.save(output_path, "JPEG", quality=95)

        log_entry = {
            "filename": original_filename,
            "swatch": swatch_filename,
            "garment_type": self.garment_type,
            "crop": {
                "x": rect.x(), 
                "y": rect.y(), 
                "width": rect.width(), 
                "height": rect.height()
            }
        }
        
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        try:
            with open(LOG_PATH, "r") as f: data = json.load(f)
            if "entries" not in data: data = {"entries": []}
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"metadata": {"version": "0.1", "description": "Logs swatch crops.", "created_by": "SwatchCropGUI"}, "entries": []}

        data["entries"] = [e for e in data["entries"] if e.get("filename") != original_filename]
        data["entries"].append(log_entry)

        with open(LOG_PATH, "w") as f: json.dump(data, f, indent=2)

        print(f"Saved: {swatch_filename}")
        self.nextImage()

    def nextImage(self):
        self.current_index += 1
        self.loadImage()
        
    def prevImage(self):
        self.current_index -= 1
        self.loadImage()
    
    def addNewGarmentType(self):
        text, ok = QtWidgets.QInputDialog.getText(self, 'Add Garment Type', 'Enter new type name:')
        if ok and text:
            new_type = text.strip()
            if new_type and new_type not in self.garment_types:
                self.garment_types.append(new_type)
                self.garment_selector.addItem(new_type)
                self.garment_selector.setCurrentText(new_type)
        self.setFocus()

    def keyPressEvent(self, event):
        step = 10
        rect = self.image_label.crop_rect
        key = event.key()

        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.saveSwatch()
        
        elif key == QtCore.Qt.Key_Tab:
            if self.original_pixmap:
                # --- FIX: Save scroll positions before showing preview ---
                self.last_scroll_h = self.scroll_area.horizontalScrollBar().value()
                self.last_scroll_v = self.scroll_area.verticalScrollBar().value()
                # --- END FIX ---
                
                self.image_label.preview_mode = True
                scaled_pixmap = self.original_pixmap.scaled(
                    self.scroll_area.viewport().size(), 
                    QtCore.Qt.KeepAspectRatio, 
                    QtCore.Qt.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.setFixedSize(self.scroll_area.viewport().size())
                
        elif key in (QtCore.Qt.Key_Equal, QtCore.Qt.Key_Plus):
            current_size = rect.width()
            new_size = current_size + step
            self.resizeCrop(new_size)
            
        elif key in (QtCore.Qt.Key_Minus, QtCore.Qt.Key_Underscore):
            current_size = rect.width()
            new_size = max(MIN_CROP_SIZE, current_size - step)
            self.resizeCrop(new_size)

        elif key == QtCore.Qt.Key_Left:
            rect.translate(-step, 0)
            self.image_label.update()
        elif key == QtCore.Qt.Key_Right:
            rect.translate(step, 0)
            self.image_label.update()
        elif key == QtCore.Qt.Key_Up:
            rect.translate(0, -step)
            self.image_label.update()
        elif key == QtCore.Qt.Key_Down:
            rect.translate(0, step)
            self.image_label.update()
        
        else:
            super().keyPressEvent(event)
            
    def resizeCrop(self, new_size):
        rect = self.image_label.crop_rect
        center = rect.center()
        new_top_left = center - QtCore.QPoint(new_size // 2, new_size // 2)
        rect.setTopLeft(new_top_left)
        rect.setSize(QtCore.QSize(new_size, new_size))
        self.image_label.update()

    def keyReleaseEvent(self, event):
        if event.key() == QtCore.Qt.Key_Tab:
            if self.original_pixmap:
                self.image_label.preview_mode = False
                self.image_label.setPixmap(self.original_pixmap)
                self.image_label.setFixedSize(self.original_pixmap.size())
                
                # --- FIX: Restore scroll positions after preview ---
                self.scroll_area.horizontalScrollBar().setValue(self.last_scroll_h)
                self.scroll_area.verticalScrollBar().setValue(self.last_scroll_v)
                # --- END FIX ---
        else:
            super().keyReleaseEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = SwatchCropper() 
    win.show()
    sys.exit(app.exec_())