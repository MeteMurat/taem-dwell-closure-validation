# store/dataSave.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class DataSave:
    """
    Geriye uyumlu veri toplayıcı.

    - multi_main.py şu an DataSave() çağırıyor => save_path zorunlu OLMAMALI.
    - multi_main sim sonunda db.data üzerinden CSV yazıyor => self.data DataFrame OLMALI.
    - np.ndarray / np.generic gibi tipler CSV'yi bozmasın diye scalar'a indirger.
    - flush_every ile buffer birikir; sim sonunda finalize() çağırınca son buffer kaybolmaz.
    """

    def __init__(self, save_path: Optional[str] = None, flush_every: int = 50):
        self.save_path = save_path  # opsiyonel: anlık CSV append isterseniz
        self.flush_every = max(1, int(flush_every))

        self._buf: List[Dict[str, Any]] = []
        self.data: pd.DataFrame = pd.DataFrame()

        self._file_header_written = False

    @staticmethod
    def _sanitize_value(v: Any) -> Any:
        # numpy scalar -> python scalar
        if isinstance(v, np.generic):
            return v.item()

        # numpy array -> scalar ise scalar'a indir; değilse list yap (CSV'de stringe döner)
        if isinstance(v, np.ndarray):
            arr = np.asarray(v)
            if arr.shape == () or arr.size == 1:
                return float(arr.reshape(-1)[0])
            return arr.reshape(-1).tolist()

        return v

    def update(self, new_data: Dict[str, Any]):
        row = dict(new_data)

        for k in list(row.keys()):
            row[k] = self._sanitize_value(row[k])

        self._buf.append(row)

        if len(self._buf) >= self.flush_every:
            self._flush()

    def _flush(self):
        if not self._buf:
            return

        df_new = pd.DataFrame(self._buf)
        self._buf.clear()

        # RAM'de biriktir (multi_main bunu kullanıyor)
        if self.data.empty:
            self.data = df_new
        else:
            self.data = pd.concat([self.data, df_new], ignore_index=True)

        # Opsiyonel: anlık dosyaya da yaz
        if self.save_path:
            out_dir = os.path.dirname(self.save_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

            file_exists = os.path.exists(self.save_path)
            mode = "a" if file_exists else "w"
            header = (not file_exists) and (not self._file_header_written)

            df_new.to_csv(self.save_path, mode=mode, header=header, index=False)
            self._file_header_written = True

    def finalize(self):
        # Sim sonunda mutlaka çağrılmalı: son buffer satırları kaybolmasın
        self._flush()
