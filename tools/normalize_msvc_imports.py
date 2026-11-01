"""Packaging-only modification: use Microsoft's separately installed VC runtime.

delvewheel renames some MSVCP imports to match bundled private copies. Restore
the import name, without changing executable instructions, before omitting all
Microsoft runtime DLLs. The replacement is shorter and fits the existing slot.
"""
import hashlib,json,re,sys
from pathlib import Path
import pefile

def normalize(root):
    root=Path(root).resolve();records=[]
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in {'.dll','.pyd','.exe'}:continue
        if re.fullmatch(r'(?:msvcp|vcruntime|concrt|vcomp)\d+(?:_\d+)?(?:-[0-9a-f]+)?\.dll',p.name,re.I):
            # These binaries are intentionally not redistributed.
            records.append({'path':p.relative_to(root).as_posix(),'operation':'omit-microsoft-runtime','sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
            p.unlink();continue
        pe=pefile.PE(str(p),fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
        image=bytearray(p.read_bytes());changes=[]
        for group in ['DIRECTORY_ENTRY_IMPORT','DIRECTORY_ENTRY_DELAY_IMPORT']:
            for entry in getattr(pe,group,[]):
                old=entry.dll
                match=re.fullmatch(rb'(msvcp\d+(?:_\d+)?)-[0-9a-f]+\.dll',old,re.I)
                if not match:continue
                new=match.group(1)+b'.dll'
                rva=getattr(entry.struct,'Name',None) or getattr(entry.struct,'szName',None)
                offset=pe.get_offset_from_rva(rva)
                assert bytes(image[offset:offset+len(old)])==old
                image[offset:offset+len(old)+1]=new+b'\0'*(len(old)+1-len(new))
                changes.append({'from':old.decode(),'to':new.decode()})
        pe.close()
        if changes:
            before=hashlib.sha256(p.read_bytes()).hexdigest();p.write_bytes(image)
            records.append({'path':p.relative_to(root).as_posix(),'operation':'normalize-dll-import-name','imports':changes,'before_sha256':before,'after_sha256':hashlib.sha256(image).hexdigest()})
    (root/'THIRD_PARTY_MODIFICATIONS.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return records
if __name__=='__main__':
    print(json.dumps(normalize(sys.argv[1]),indent=2))
