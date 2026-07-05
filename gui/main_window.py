from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QMessageBox, QTableWidget,
    QTableWidgetItem, QHBoxLayout
)
from processor import Processor
from utils.app import APP_NAME, APP_VERSION


class MainWindow(QMainWindow):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 720)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("Імпорт накладних Coca-Cola")
        title.setStyleSheet("font-size:22px;font-weight:bold")
        layout.addWidget(title)
        grid = QGridLayout()
        layout.addLayout(grid)
        self.ed_products = self._row(grid, 0, "Товари.xlsx", settings.products_file, self.pick_file)
        self.ed_shops = self._row(grid, 1, "Адреси.xlsx", settings.shops_file, self.pick_file)
        self.ed_input = self._row(grid, 2, "Папка input", settings.input_dir, self.pick_dir)
        self.ed_output = self._row(grid, 3, "Папка output", settings.output_dir, self.pick_dir)
        btns = QHBoxLayout()
        layout.addLayout(btns)
        self.btn_scan = QPushButton("Сканувати")
        self.btn_scan.clicked.connect(self.scan)
        self.btn_process = QPushButton("Обробити")
        self.btn_process.clicked.connect(self.process)
        btns.addWidget(self.btn_scan)
        btns.addWidget(self.btn_process)
        btns.addStretch()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Файл", "Стор.", "Статус", "Рядків"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.log_msg("Готово до роботи")

    def _row(self, grid, row, label, value, picker):
        grid.addWidget(QLabel(label), row, 0)
        edit = QLineEdit(value)
        grid.addWidget(edit, row, 1)
        btn = QPushButton("...")
        btn.clicked.connect(lambda: picker(edit))
        grid.addWidget(btn, row, 2)
        return edit

    def pick_file(self, edit):
        fn, _ = QFileDialog.getOpenFileName(self, "Вибір Excel", edit.text(), "Excel (*.xlsx)")
        if fn: edit.setText(fn)

    def pick_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "Вибір папки", edit.text())
        if d: edit.setText(d)

    def save_settings(self):
        self.settings.set("folders", "products", self.ed_products.text())
        self.settings.set("folders", "shops", self.ed_shops.text())
        self.settings.set("folders", "input", self.ed_input.text())
        self.settings.set("folders", "output", self.ed_output.text())
        self.settings.save()

    def log_msg(self, s):
        self.log.append(str(s))

    def scan(self):
        self.save_settings()
        p = Processor(self.settings, self.log_msg)
        files = p.files()
        self.table.setRowCount(0)
        for f in files:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(f.name))
            self.table.setItem(r, 1, QTableWidgetItem(""))
            self.table.setItem(r, 2, QTableWidgetItem("очікує"))
            self.table.setItem(r, 3, QTableWidgetItem(""))
        self.log_msg(f"Знайдено файлів: {len(files)}")

    def process(self):
        try:
            self.save_settings()
            self.log_msg("=== Початок обробки ===")
            p = Processor(self.settings, self.log_msg)
            invoices = p.run()
            self.table.setRowCount(0)
            for inv in invoices:
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(inv.source_file))
                self.table.setItem(r, 1, QTableWidgetItem(str(inv.page)))
                self.table.setItem(r, 2, QTableWidgetItem(f"DOC={inv.doc}; SHOP={(inv.shop.code if inv.shop else '')}"))
                self.table.setItem(r, 3, QTableWidgetItem(str(len(inv.items))))
            QMessageBox.information(self, "Готово", "Обробку завершено")
        except Exception as e:
            QMessageBox.critical(self, "Помилка", str(e))
            self.log_msg(f"ПОМИЛКА: {e}")
