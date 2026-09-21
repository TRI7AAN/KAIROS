"""Tests for CTU-13 labeled bidirectional flow adaptation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from pipeline.ctu13_flow import FEATURE_NAMES, load_ctu13_windows


HEADER = (
    "StartTime,Dur,Proto,SrcAddr,Sport,Dir,DstAddr,Dport,State,"
    "sTos,dTos,TotPkts,TotBytes,SrcBytes,Label\n"
)


class Ctu13FlowTest(unittest.TestCase):
    def test_windows_and_from_botnet_policy(self):
        rows = (
            "2011/08/18 15:39:35.000000,1.0,tcp,10.0.0.1,1,<->,"
            "10.0.0.2,80,CON,0,0,2,200,120,flow=Background\n"
            "2011/08/18 15:39:45.000000,2.0,udp,10.0.0.3,2,->,"
            "10.0.0.4,53,CON,0,0,4,400,300,"
            "flow=From-Botnet-V52-1-UDP\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.binetflow"
            path.write_text(HEADER + rows)
            result = load_ctu13_windows(path, window_seconds=10)
        self.assertEqual(result.rows, 2)
        self.assertEqual(result.features.shape, (2, len(FEATURE_NAMES)))
        self.assertEqual(result.malicious.tolist(), [0, 1])
        self.assertEqual(result.malicious_flow_count.tolist(), [0, 1])

    def test_to_botnet_is_not_marked_malicious(self):
        row = (
            "2011/08/18 15:39:35.000000,1.0,tcp,10.0.0.1,1,<->,"
            "10.0.0.2,80,CON,0,0,2,200,120,flow=To-Botnet-V52-1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.binetflow"
            path.write_text(HEADER + row)
            result = load_ctu13_windows(path)
        self.assertEqual(result.malicious.tolist(), [0])


if __name__ == "__main__":
    unittest.main()
