# Method

The analyzer separates **data reduction** from **LLM reasoning**. It first projects the smallest useful set of fields, identifies material rows, then selectively enriches only those rows. This avoids giving the LLM millions of irrelevant cells and makes the resulting evidence reproducible.
