from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, List

LOGGER = logging.getLogger(__name__)


class Translator:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self._translator = None
        self.available = False
        self._cache = {}
        self._init_argos()

    def _init_argos(self) -> None:
        try:
            os.environ.setdefault("ARGOS_PACKAGES_DIR", str((self.cache_dir / "argos_models").resolve()))
            import argostranslate.package as package
            import argostranslate.translate as translate

            installed = translate.get_installed_languages()
            en = next((l for l in installed if l.code == "en"), None)
            zh = next((l for l in installed if l.code == "zh"), None)
            if en and zh and en.get_translation(zh):
                self._translator = en.get_translation(zh)
                self.available = True
                return

            LOGGER.info("Argos en->zh model not found. Attempting one-time download/install...")
            package.update_package_index()
            packages = package.get_available_packages()
            chosen = next((p for p in packages if p.from_code == "en" and p.to_code == "zh"), None)
            if not chosen:
                LOGGER.warning("No Argos en->zh package found in index.")
                return
            download_path = chosen.download()
            package.install_from_path(download_path)

            installed = translate.get_installed_languages()
            en = next((l for l in installed if l.code == "en"), None)
            zh = next((l for l in installed if l.code == "zh"), None)
            if en and zh:
                self._translator = en.get_translation(zh)
                self.available = self._translator is not None
        except Exception as exc:
            LOGGER.warning("Translation unavailable, falling back to EN only: %s", exc)
            self.available = False

    def translate(self, text: str) -> str:
        if not text:
            return ""
        if text in self._cache:
            return self._cache[text]
        if not self.available or self._translator is None:
            return ""
        try:
            out = self._translator.translate(text)
            self._cache[text] = out
            return out
        except Exception as exc:
            LOGGER.warning("Translation failed for text fragment; using empty zh text. Error: %s", exc)
            return ""

    def translate_many(self, items: Iterable[str]) -> List[str]:
        return [self.translate(item) for item in items]
