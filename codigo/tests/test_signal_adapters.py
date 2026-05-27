import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import savemat

from codigo.app.services.signal_adapters import (
    load_signal_channel,
    read_signal_channels,
    read_signal_frame,
)


class SignalAdapterTests(unittest.TestCase):
    def test_reads_cwru_mat_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "97.mat"
            savemat(
                path,
                {
                    "X097_DE_time": np.array([[1.0], [2.0]]),
                    "X097RPM": np.array([[1797]]),
                },
            )

            channels = read_signal_channels(path)

        self.assertEqual(sorted(channels), ["DE_time", "RPM"])
        self.assertEqual(channels["DE_time"].source_key, "X097_DE_time")
        np.testing.assert_array_equal(
            channels["DE_time"].values,
            np.array([1.0, 2.0]),
        )

    def test_reads_csv_numeric_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.csv"
            pd.DataFrame(
                {"sensor_a": [1, 2, 3], "label": ["a", "b", "c"]}
            ).to_csv(path, index=False)

            signal = load_signal_channel(path, "sensor_a")

        np.testing.assert_array_equal(signal, np.array([1.0, 2.0, 3.0]))

    def test_reads_nasa_ims_timestamp_file_without_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2003.10.22.12.06.24"
            path.write_text("0.1\t0.2\n0.3\t0.4\n", encoding="utf-8")

            channels = read_signal_channels(path)

        self.assertEqual(sorted(channels), ["channel_1", "channel_2"])
        np.testing.assert_array_equal(
            channels["channel_1"].values,
            np.array([0.1, 0.3]),
        )

    def test_reads_nasa_ims_timestamp_file_as_dataframe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2004.02.12.10.32.39"
            path.write_text("0.1 0.2 0.3 0.4\n", encoding="utf-8")

            frame = read_signal_frame(path)

        self.assertEqual(
            list(frame.columns),
            ["channel_1", "channel_2", "channel_3", "channel_4"],
        )
        self.assertEqual(frame.shape, (1, 4))

    def test_unsupported_extension_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signals.bin"
            path.write_bytes(b"raw")

            with self.assertRaises(ValueError):
                read_signal_channels(path)


if __name__ == "__main__":
    unittest.main()
