import glob
import re
import tokenize
import io


def _get_docstring_positions(content):
    """Return list of (start_pos, end_pos) for docstrings in content."""
    skip_ranges = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
        for i, token in enumerate(tokens):
            if token.type == tokenize.STRING:
                # Check if this is a docstring (follows indent/def/class/colon)
                if i > 0:
                    prev = tokens[i-1]
                    # Docstring follows INDENT, NEWLINE, or DEDENT
                    if prev.type in (tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.DEDENT):
                        # Convert row/col to character offset
                        lines = content.split('\n')
                        start_pos = sum(len(lines[j]) + 1 for j in range(token.start[0] - 1)) + token.start[1]
                        end_pos = sum(len(lines[j]) + 1 for j in range(token.end[0] - 1)) + token.end[1]
                        skip_ranges.append((start_pos, end_pos))
    except:
        pass
    return skip_ranges


def test_all_requests_have_timeout():
    """Fail if requests.get or requests.post found without timeout param."""
    pattern = r'requests\.(get|post)\s*\('

    errors = []
    for py_file in glob.glob('src/**/*.py', recursive=True):
        with open(py_file, 'r', encoding='utf-8') as f:
            content = f.read()

        skip_ranges = _get_docstring_positions(content)

        # Find all requests calls
        for match in re.finditer(pattern, content):
            start = match.start()

            # Check if this match is inside a docstring
            skip = False
            for skip_start, skip_end in skip_ranges:
                if skip_start <= start <= skip_end:
                    skip = True
                    break

            if skip:
                continue

            line_num = content[:start].count('\n') + 1

            # Find closing paren for this call
            depth = 1
            pos = match.end()
            while pos < len(content) and depth > 0:
                if content[pos] == '(':
                    depth += 1
                elif content[pos] == ')':
                    depth -= 1
                pos += 1

            call_text = content[start:pos]
            if 'timeout' not in call_text:
                errors.append(f"{py_file}:{line_num} missing timeout in requests call")

    assert not errors, f"Found {len(errors)} requests calls without timeout:\n" + "\n".join(errors)
