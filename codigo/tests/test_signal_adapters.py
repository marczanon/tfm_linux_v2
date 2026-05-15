import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import savemat

from codigo.app.services.signal_adapters import load_signal_channel, read_signal_channels


class SignalAdapterTests(unittest.TestCase):
    def test_reads_cwru_mat_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "97.mat"
            savemat(path, {"X097_DE_time": np.array([[1.0], [2.0]]), "X097RPM": np.array([[1797]])})

            channels = read_signal_channels(path)

        self.assertEqual(sorted(channels), ["DE_time", "RPM"])
        self.assertEqual(channels["DE_time"].source_key, "X097_DE_time")
        np.testing.assert_array_equal(channels["DE_time"].values, np.array([1.0, 2.0]))

    def test_reads_csv_numeric_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.csv"
            pd.DataFrame({"sensor_a": [1, 2, 3], "label": ["a", "b", "c"]}).to_csv(path, index=False)

            signal = load_signal_channel(path, "sensor_a")

        np.testing.assert_array_equal(signal, np.array([1.0, 2.0, 3.0]))

    def test_unsupported_extension_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.bin"
            path.write_bytes(b"raw")

            with self.assertRaises(ValueError):
                read_signal_channels(path)


if __name__ == "__main__":
    unittest.main()
