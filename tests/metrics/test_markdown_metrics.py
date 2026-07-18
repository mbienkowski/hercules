"""Unit tests for the markdown metrics module — instruction and table-row counting."""

from tests.metrics.markdown_metrics import count_instructions, count_status_table_rows


def test_instructions_shown_only_as_a_code_example_are_not_counted():
    """When an instruction appears inside a fenced code example (shown to illustrate the
    format, not as a real instruction to follow), it must not be counted. Otherwise the
    same instruction would be counted twice -- once as the example, once for real."""
    # Given
    md = (
        "1. real instruction\n"
        "- a bullet\n"
        "| table | row |\n"
        "```\n"
        "1. fenced not counted\n"
        "- fenced bullet\n"
        "```\n"
        "plain prose\n"
        "2. another instruction"
    )

    # When
    count = count_instructions(md)

    # Then
    assert count == 3  # "1.", "- a bullet", "2." — table + fenced excluded


def test_rows_of_a_table_are_not_mistaken_for_instructions():
    """A table's rows are data, not action items, so they must not be counted alongside
    numbered or bulleted instructions -- otherwise a document with a table would report
    more instructions than it actually contains."""
    # Given
    md = "| col1 | col2 |\n|---|---|\n| val1 | val2 |\n- bullet after table"

    # When
    count = count_instructions(md)

    # Then
    assert count == 1  # only the bullet


def test_counting_a_status_table_reports_only_its_data_entries():
    """A status table has a header row and a separator line before its real entries begin.
    The count must reflect only those entries -- including the header or separator would
    overstate how many statuses were actually reported."""
    # Given
    md = (
        "prose\n"
        "| STATUS | Meaning | ACTION |\n"
        "|---|---|---|\n"
        "| Blocker | x | y |\n"
        "| High | x | y |\n"
        "\nafter"
    )

    # When
    count = count_status_table_rows(md)

    # Then
    assert count == 2


def test_a_document_with_no_status_table_is_reported_as_such():
    """When the text contains no status table (no STATUS / Meaning / ACTION header) at all,
    the count must clearly signal 'no table found' rather than reporting zero -- so a caller
    can tell the difference between 'no table present' and 'table present but empty'."""
    # Given
    md = "no table here"

    # When
    count = count_status_table_rows(md)

    # Then
    assert count == -1


def test_a_table_with_different_column_headers_is_not_mistaken_for_the_status_table():
    """A table that looks like a table but uses different column headers is not the status
    table, so it must be reported as 'no status table found' rather than having its rows
    counted as if they were status entries."""
    # Given — a valid markdown table but with different column names
    md = (
        "| Name | Value | Description |\n"
        "|---|---|---|\n"
        "| foo | 1 | bar |\n"
        "| baz | 2 | qux |\n"
    )

    # When
    count = count_status_table_rows(md)

    # Then — no STATUS header found, must return sentinel -1
    assert count == -1


def test_counting_stops_at_the_end_of_the_status_table_even_if_another_one_follows():
    """Once the status table ends, counting must stop there -- so if the document later
    contains a second status table, its rows are never folded into the first table's count."""
    # Given
    md = (
        "| STATUS | Meaning | ACTION |\n"
        "|---|---|---|\n"
        "| Blocker | fatal | abort |\n"
        "| High | serious | fix |\n"
        "\n"
        "prose after table\n"
        "| STATUS | Meaning | ACTION |\n"  # second table — must not be counted
        "|---|---|---|\n"
        "| Pass | ok | continue |\n"
    )

    # When
    count = count_status_table_rows(md)

    # Then — only 2 rows from the first table, stops at blank line
    assert count == 2
