"""Unit tests for the markdown metrics module — instruction and table-row counting."""

from tests.metrics.markdown_metrics import count_instructions, count_status_table_rows


def test_fenced_code_regions_are_not_counted_as_instructions():
    """Instructions inside fenced blocks are invisible to users and must not be counted."""
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


def test_table_rows_are_not_counted_as_instructions():
    """Markdown table rows start with | and must be excluded from instruction counts."""
    # Given
    md = "| col1 | col2 |\n|---|---|\n| val1 | val2 |\n- bullet after table"

    # When
    count = count_instructions(md)

    # Then
    assert count == 1  # only the bullet


def test_status_table_row_count_returns_the_number_of_data_rows():
    """Data rows below the separator are counted; header and separator are not."""
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


def test_status_table_row_count_returns_minus_one_when_table_is_absent():
    """When no STATUS | Meaning | ACTION header exists, -1 signals 'no table found'."""
    # Given
    md = "no table here"

    # When
    count = count_status_table_rows(md)

    # Then
    assert count == -1


def test_status_table_row_count_returns_minus_one_for_non_status_table():
    """A table without STATUS | Meaning | ACTION headers must return -1, not count its rows."""
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


def test_status_table_counting_stops_at_non_table_row():
    """Row counting must stop at the first line that doesn't start with '|'."""
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
