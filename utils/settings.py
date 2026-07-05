from configparser import ConfigParser
from pathlib import Path


class Settings:
    def __init__(self, filename="config.ini"):
        self.filename = Path(filename)
        self.cfg = ConfigParser()
        self._defaults()
        if self.filename.exists():
            self.cfg.read(self.filename, encoding="utf-8")
        else:
            self.save()

    def _defaults(self):
        self.cfg["folders"] = {
            "input": "input",
            "output": "output",
            "products": "data/Товари.xlsx",
            "shops": "data/Адреси.xlsx",
        }
        self.cfg["ocr"] = {
            "language": "ukr+eng",
            "dpi": "300",
            "psm": "6",
            "oem": "3",
            "save_debug": "true",
        }

    def save(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            self.cfg.write(f)

    def get(self, section, key):
        return self.cfg.get(section, key)

    def set(self, section, key, value):
        self.cfg.set(section, key, str(value))

    @property
    def input_dir(self): return self.get("folders", "input")
    @property
    def output_dir(self): return self.get("folders", "output")
    @property
    def products_file(self): return self.get("folders", "products")
    @property
    def shops_file(self): return self.get("folders", "shops")
    @property
    def ocr_language(self): return self.get("ocr", "language")
    @property
    def dpi(self): return self.cfg.getint("ocr", "dpi")
    @property
    def psm(self): return self.cfg.getint("ocr", "psm")
    @property
    def oem(self): return self.cfg.getint("ocr", "oem")
    @property
    def save_debug(self): return self.cfg.getboolean("ocr", "save_debug")
