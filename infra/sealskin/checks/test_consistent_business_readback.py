"""Regression cases execute the real SQLite readback block on scratch databases."""
from pathlib import Path
import sqlite3
import tempfile
import textwrap
import unittest

SOURCE = Path(__file__).with_name('consistent-business-readback.py').read_text()
BLOCK = textwrap.dedent(SOURCE[SOURCE.index('  db=sqlite3.connect(copy.as_uri()'):SOURCE.index('\nconfig=json.loads')])


class SQLiteReadbackTest(unittest.TestCase):
    def readback(self, collation='', invalid_schema=False):
        with tempfile.TemporaryDirectory(prefix='business-sqlite-') as tmp:
            directory = Path(tmp) / 'escaped#uri?'
            directory.mkdir()
            path = directory / ('suggest.sqlite' if collation else 'ordinary.sqlite')
            db = sqlite3.connect(str(path))
            if collation:
                db.create_collation(collation, lambda a, b: (a > b) - (a < b))
            db.execute('CREATE TABLE sample(value TEXT' + (' COLLATE ' + collation if collation else '') + ')')
            db.execute('CREATE INDEX sample_value ON sample(value)')
            db.executemany('INSERT INTO sample VALUES (?)', [('first',), ('second',)])
            if invalid_schema:
                db.execute('PRAGMA writable_schema=ON')
                db.execute("UPDATE sqlite_master SET sql='INVALID SCHEMA' WHERE name='sample'")
            db.commit()
            db.close()
            results = {'sqlite': []}
            namespace = dict(copy=path, path=path, name=path.name, sqlite3=sqlite3, results=results)
            try:
                exec(BLOCK, namespace)
                return results['sqlite'][0], namespace['require_native_comparator']
            finally:
                if namespace.get('db'):
                    namespace['db'].close()

    def test_escaped_uri_and_ordinary_integrity(self):
        result, _ = self.readback()
        self.assertEqual(result['quick_check'], 'ok')
        self.assertIsNone(result['native_collation'])

    def test_native_names_allow_reading_without_fabricated_comparisons(self):
        for name in ['geonames_collate', 'i18n_collate']:
            with self.subTest(collation=name):
                result, compare = self.readback(name)
                self.assertEqual(result['quick_check'], 'ok')
                self.assertEqual(result['counts'], {'sample': 2})
                self.assertEqual(result['native_comparator_calls'], 0)
                with self.assertRaisesRegex(RuntimeError, 'native collation'):
                    compare('first', 'second')

    def test_unknown_collation_is_rejected(self):
        with self.assertRaises(sqlite3.OperationalError):
            self.readback('unknown_collation')

    def test_bad_schema_is_rejected(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.readback(invalid_schema=True)


if __name__ == '__main__':
    unittest.main()
