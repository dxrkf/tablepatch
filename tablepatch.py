#!/usr/bin/env python3
"""Key-aware CSV changes with reproducible, baseline-checked patches."""
import argparse
import csv
import hashlib
import html
import io
import json
import sys
from pathlib import Path


def validate(columns, rows, key):
    if not isinstance(columns, list) or not columns or any(not isinstance(c, str) or not c for c in columns):
        raise ValueError('columns must be nonempty strings')
    if len(set(columns)) != len(columns) or key not in columns:
        raise ValueError('duplicate headers or missing key column')
    for k, row in rows.items():
        if not isinstance(row, dict) or set(row) != set(columns) or any(not isinstance(v, str) for v in row.values()):
            raise ValueError('row does not match columns')
        if not k or not k.strip() or row[key] != k:
            raise ValueError('empty or inconsistent row key')


def read_csv(path, key, delimiter=','):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        columns = next(reader, None)
        validate(columns, {}, key)
        rows = {}
        for values in reader:
            if not values:
                continue
            if len(values) != len(columns):
                raise ValueError('row width differs from header near CSV line ' + str(reader.line_num))
            row = dict(zip(columns, values))
            identity = row[key]
            if identity in rows:
                raise ValueError('duplicate row key near CSV line ' + str(reader.line_num))
            rows[identity] = row
        validate(columns, rows, key)
    return columns, rows


def fingerprint(columns, rows):
    logical = dict(columns=sorted(columns), rows=[rows[k] for k in sorted(rows)])
    raw = json.dumps(logical, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def compare(before, after, key):
    bc, br = before
    ac, ar = after
    validate(bc, br, key)
    validate(ac, ar, key)
    return dict(format='tablepatch-v1', key=key, before_columns=bc, after_columns=ac,
                before_sha256=fingerprint(bc, br), after_sha256=fingerprint(ac, ar),
                added=[ar[k] for k in sorted(ar.keys()-br.keys())],
                removed=[br[k] for k in sorted(br.keys()-ar.keys())],
                updated=[dict(key=k, before=br[k], after=ar[k]) for k in sorted(br.keys() & ar.keys()) if br[k] != ar[k]])


def apply_patch(before, patch):
    required = {'format','key','before_columns','after_columns','before_sha256','after_sha256','added','removed','updated'}
    if not isinstance(patch, dict) or set(patch) != required or patch['format'] != 'tablepatch-v1':
        raise ValueError('unsupported patch schema')
    key = patch['key']
    if not isinstance(key, str):
        raise ValueError('invalid patch key')
    columns, original = before
    validate(columns, original, key)
    validate(patch['before_columns'], {}, key)
    validate(patch['after_columns'], {}, key)
    if set(columns) != set(patch['before_columns']) or fingerprint(columns, original) != patch['before_sha256']:
        raise ValueError('baseline mismatch: patch was built from different data')
    rows = {k: dict(v) for k, v in original.items()}
    touched = set()
    def claim(identity):
        if not isinstance(identity, str) or identity in touched:
            raise ValueError('duplicate or invalid operation key')
        touched.add(identity)
    for field in ('added','removed','updated'):
        if not isinstance(patch[field], list):
            raise ValueError('patch operations must be arrays')
    for old in patch['removed']:
        if not isinstance(old, dict) or key not in old:
            raise ValueError('invalid removal')
        identity=old[key]; claim(identity)
        if rows.get(identity) != old:
            raise ValueError('removal precondition failed')
        del rows[identity]
    for update in patch['updated']:
        if not isinstance(update, dict) or set(update) != {'key','before','after'}:
            raise ValueError('invalid update')
        identity=update['key']; claim(identity)
        if rows.get(identity) != update['before']:
            raise ValueError('update precondition failed')
        rows[identity]=update['after']
    for row in patch['added']:
        if not isinstance(row, dict) or key not in row:
            raise ValueError('invalid addition')
        identity=row[key]; claim(identity)
        if identity in rows:
            raise ValueError('addition already exists')
        rows[identity]=row
    validate(patch['after_columns'], rows, key)
    if fingerprint(patch['after_columns'], rows) != patch['after_sha256']:
        raise ValueError('target fingerprint mismatch: patch is incomplete or altered')
    return patch['after_columns'], rows


def csv_text(table, delimiter=','):
    columns, rows=table
    out=io.StringIO(newline='')
    writer=csv.DictWriter(out, fieldnames=columns, delimiter=delimiter, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows[k] for k in sorted(rows))
    return out.getvalue()


def report_html(patch):
    counts = {k:len(patch[k]) for k in ('added','removed','updated')}
    data=html.escape(json.dumps(patch, indent=2, ensure_ascii=True))
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>TablePatch review</title><style>body{font:17px system-ui;background:#0d1423;color:#e2e8f0;max-width:1100px;margin:50px auto;padding:24px}h1{color:#5eead4}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#18263c;padding:24px;border-radius:16px}</style><h1>TablePatch / CSV change review</h1><p>''' + html.escape(' | '.join(f'{k}: {v}' for k,v in counts.items())) + '</p><p>Cell values are exact strings. Row and column order do not affect data fingerprints.</p><pre>' + data + '</pre></html>'


def write_new(path, content):
    # Exclusive creation refuses existing files, symlinks and input paths.
    with Path(path).open('x', encoding='utf-8', newline='') as stream:
        stream.write(content)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command', required=True)
    diff=sub.add_parser('diff', help='compare tables and optionally save a patch/report')
    diff.add_argument('before'); diff.add_argument('after'); diff.add_argument('--key',required=True)
    diff.add_argument('--patch'); diff.add_argument('--html'); diff.add_argument('--check', action='store_true')
    apply=sub.add_parser('apply', help='apply a verified patch to a new output CSV')
    apply.add_argument('before'); apply.add_argument('patch'); apply.add_argument('--output',required=True)
    for p in (diff,apply):p.add_argument('--delimiter',default=',')
    args=parser.parse_args()
    try:
        if len(args.delimiter)!=1 or args.delimiter in '\r\n"':
            raise ValueError('delimiter must be one character other than quote or newline')
        if args.command=='diff':
            before=read_csv(args.before,args.key,args.delimiter)
            after=read_csv(args.after,args.key,args.delimiter)
            patch=compare(before,after,args.key)
            # Validate all output destinations before writing either artifact.
            destinations=[Path(p) for p in (args.patch,args.html) if p]
            if len({p.resolve() for p in destinations})!=len(destinations):
                raise ValueError('output paths must be distinct')
            if any(p.exists() or p.is_symlink() for p in destinations):
                raise ValueError('output already exists; choose a new path')
            if args.patch:write_new(args.patch,json.dumps(patch,indent=2,ensure_ascii=True)+'\n')
            if args.html:write_new(args.html,report_html(patch))
            counts={k:len(patch[k]) for k in ('added','removed','updated')}
            print('TablePatch: '+', '.join(str(v)+' '+k for k,v in counts.items()))
            schema_changed=set(patch['before_columns'])!=set(patch['after_columns'])
            print('Schema changed: '+str(schema_changed).lower())
            print('Inputs unchanged. Row order ignored. Cell values compared exactly.')
            return int(args.check and (any(counts.values()) or schema_changed))
        patch=json.loads(Path(args.patch).read_text(encoding='utf-8'))
        before=read_csv(args.before,patch.get('key') if isinstance(patch,dict) else '',args.delimiter)
        result=apply_patch(before,patch)
        write_new(args.output,csv_text(result,args.delimiter))
        print('Applied patch: '+str(len(result[1]))+' rows. Target fingerprint verified.')
        print('Created a new CSV. Existing files were not overwritten.')
        return 0
    except (OSError, ValueError, TypeError, KeyError, csv.Error) as exc:
        print('error: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':sys.exit(main())
