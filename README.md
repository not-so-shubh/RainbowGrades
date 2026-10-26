# RainbowGrades

RainbowGrades reads Submitty's student summary JSON and produces instructor and
individual grade reports. A course Makefile includes `MakefileHelper`; its
`compile` target builds the C++11 program with the pinned nlohmann/json headers.

## Optional contact information

Student summaries may contain `linkedin_username`, `github_username`, and
`personal_webpage`. Missing, null, or empty values produce empty cells. Other
non-string values are errors with a nonzero exit status. Existing summaries
without these keys remain supported.

Add any of those exact names to the customization JSON's `display` array to show
the corresponding instructor HTML column. All three default to disabled and
are excluded from individual student reports. Valid identifiers link to LinkedIn
or GitHub; personal links require HTTP/HTTPS, a host, and no credentials. Invalid
historical strings are displayed as escaped text, without fetching any URL.
Hostname checks accept ASCII DNS names (including punycode) and bracketed IPv6
literals; IPv6 zone identifiers are not linked.

Instructor CSV always appends all three contact columns, independently of the
HTML options. Contact cells preserve commas, quotes, and line breaks using CSV
quoting. Formula-leading characters and leading control/whitespace prefixes
receive a protective apostrophe, including common UTF-8 whitespace and BOM
prefixes. Existing numeric grade serialization is unchanged.
Historical NUL bytes are rendered as the two literal characters `\0`; formula
protection still uses the original leading character. Other text is unchanged.

Deploy a compatible RainbowGrades revision before Submitty begins emitting
these keys or enabling these display options. Coordinate Submitty's dependency
pin with an actual compatible consumer release; an older consumer rejects the
new keys even when every value is empty.

## Synthetic regression tests

No database, live course data, network access, or additional Python packages are
needed. Supply an already available nlohmann/json **v3.12.0** include directory:

```sh
python3 tests/test_contact_info.py --json-include /path/to/existing/include -v
```

The runner compiles with `clang++` (`--cxx` overrides it) and runs only in fresh
temporary directories. It checks parsing, all display combinations, privacy,
links, CSV safety, and existing numeric cells. Use `--artifacts /path/to/new/results`
to retain the executable, logs, inputs and outputs; that directory must not exist.
An optional `--baseline-executable /path/to/unmodified/process_grades.out` adds
old/new compatibility controls and compares the established CSV columns.
For this feature, build that executable from the exact unmodified parent commit
`a126039d45f4bd82ab8064414972aa11136e1824`. A VM's older pinned revision is
not a valid baseline for that strict comparison.

Do not use `make all`, `make pull`, or `make push` for these tests: those targets
access configured course reports. `make test` selects the test-grade sorting
mode; it is not this regression suite.
