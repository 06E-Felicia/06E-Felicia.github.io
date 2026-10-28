"""Archive launcher safety and integrity checks; no NumPy or model run."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from simulation.test_replay import validate_archive


class TestReplayLauncherTests(unittest.TestCase):
    def archive(self,root):
        body=b'{"actual":"test data"}'
        (root/'astra-20261017.json').write_bytes(body)
        index={'schema':'stormsim-astra-test-v1','status':'complete','cases':[
            {'file':'astra-20261017.json','sha256':hashlib.sha256(body).hexdigest()}]}
        (root/'index.json').write_text(json.dumps(index));return index

    def test_complete_archive_is_checked_without_scientific_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);expected=self.archive(root)
            self.assertEqual(validate_archive(root),expected)

    def test_missing_or_unfinished_archive_is_not_silently_recomputed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaisesRegex(RuntimeError,'不会重新随机计算'):validate_archive(root)
            d=self.archive(root);d['status']='running'
            (root/'index.json').write_text(json.dumps(d))
            with self.assertRaisesRegex(RuntimeError,'未完成'):validate_archive(root)

    def test_changed_frame_bundle_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.archive(root)
            (root/'astra-20261017.json').write_text('different run')
            with self.assertRaisesRegex(RuntimeError,'校验失败'):validate_archive(root)

    def test_parent_or_duplicate_archive_paths_are_rejected(self):
        for bad in ['../astra-20261017.json','https://example.com/astra-20261017.json']:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);d=self.archive(root);d['cases'][0]['file']=bad
                (root/'index.json').write_text(json.dumps(d))
                with self.assertRaisesRegex(RuntimeError,'路径无效'):validate_archive(root)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);d=self.archive(root);d['cases']*=2
            (root/'index.json').write_text(json.dumps(d))
            with self.assertRaisesRegex(RuntimeError,'路径无效'):validate_archive(root)


if __name__=='__main__':unittest.main()
