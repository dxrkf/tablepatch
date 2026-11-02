import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tablepatch import compare, apply_patch, fingerprint, read_csv, csv_text, report_html, write_new


def table(values,columns=None):
    cols=columns or ['id','name']
    return cols,{r['id']:r for r in values}


class TableTests(unittest.TestCase):
    def setUp(self):
        self.before=table([{'id':'1','name':'A'},{'id':'2','name':'B'}])
        self.after=table([{'id':'2','name':'Bee'},{'id':'3','name':'C'}])
    def test_changes(self):
        p=compare(self.before,self.after,'id')
        self.assertEqual([len(p[x]) for x in ('added','removed','updated')],[1,1,1])
    def test_roundtrip(self):
        p=compare(self.before,self.after,'id')
        self.assertEqual(apply_patch(self.before,p),self.after)
    def test_baseline_drift(self):
        p=compare(self.before,self.after,'id')
        bad=table([{'id':'1','name':'changed'},{'id':'2','name':'B'}])
        with self.assertRaises(ValueError):apply_patch(bad,p)
    def test_tampering(self):
        p=compare(self.before,self.after,'id');p['added'][0]['name']='tampered'
        with self.assertRaises(ValueError):apply_patch(self.before,p)
    def test_order_ignored(self):
        other=(['name','id'],dict(reversed(list(self.before[1].items()))))
        p=compare(self.before,other,'id')
        self.assertEqual(p['before_sha256'],p['after_sha256']);self.assertEqual(p['updated'],[])
    def test_schema_change(self):
        other=table([{'id':'1','city':'Riyadh'}],['id','city'])
        self.assertEqual(apply_patch(self.before,compare(self.before,other,'id')),other)
    def test_duplicate_operation(self):
        p=compare(self.before,self.after,'id');p['added'].append(copy.deepcopy(p['added'][0]))
        with self.assertRaises(ValueError):apply_patch(self.before,p)
    def test_html_escaping(self):
        other=table([{'id':'1','name':'<script>alert(1)</script>'}])
        self.assertNotIn('<script>',report_html(compare(self.before,other,'id')))
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x';p.write_text('keep')
            with self.assertRaises(FileExistsError):write_new(p,'replace')
            self.assertEqual(p.read_text(),'keep')
    def test_csv_quotes_unicode_multiline_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.csv';p.write_text('\ufeffid,name\n1,"مرحبا,\nالعالم"\n',encoding='utf-8')
            t=read_csv(p,'id');self.assertEqual(t[1]['1']['name'],'مرحبا,\nالعالم')
            p.write_text(csv_text(t),encoding='utf-8');self.assertEqual(read_csv(p,'id'),t)
    def test_reject_duplicate_keys(self):
        self.reject('id,name\n1,A\n1,B\n')
    def test_reject_duplicate_headers(self):self.reject('id,id\n1,2\n')
    def test_reject_bad_width(self):self.reject('id,name\n1,A,extra\n')
    def test_reject_empty_key(self):self.reject('id,name\n,A\n')
    def reject(self,text):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.csv';p.write_text(text)
            with self.assertRaises(ValueError):read_csv(p,'id')
    def test_empty_schema_only(self):
        p=compare((['id','name'],{}),(['id','city'],{}),'id')
        self.assertNotEqual(p['before_sha256'],p['after_sha256'])
        self.assertEqual(apply_patch((['id','name'],{}),p),(['id','city'],{}))
    def test_cli_flow(self):
        script=str(Path(__file__).with_name('tablepatch.py'))
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);b=d/'b.csv';a=d/'a.csv';p=d/'p.json';o=d/'out.csv'
            b.write_text(csv_text(self.before));a.write_text(csv_text(self.after))
            run=subprocess.run([sys.executable,script,'diff',str(b),str(a),'--key','id','--patch',str(p),'--check'],capture_output=True)
            self.assertEqual(run.returncode,1)
            run=subprocess.run([sys.executable,script,'apply',str(b),str(p),'--output',str(o)],capture_output=True)
            self.assertEqual(run.returncode,0);self.assertEqual(read_csv(o,'id'),self.after)
            run=subprocess.run([sys.executable,script,'apply',str(b),str(p),'--output',str(o)],capture_output=True)
            self.assertEqual(run.returncode,2)

if __name__=='__main__':unittest.main()
