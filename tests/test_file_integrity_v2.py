import py_compile, glob, pathlib

def test_all_py_compile():
    errs = [f for f in glob.glob("src/**/*.py", recursive=True)
            if not py_compile.compile(f, doraise=False)]
    assert not errs, f"Syntax errors: {errs}"

def test_no_null_bytes():
    bad = [f for f in glob.glob("src/**/*.py", recursive=True)
           if b"\x00" in pathlib.Path(f).read_bytes()]
    assert not bad, f"Null bytes: {bad}"
