# Reflection

I kept searching and saving separate because asking about a book should not
automatically add it to the reading list. `search_catalog` only reads the seeded
catalog, while `save_to_reading_list` checks a book ID and saves it in SQLite.
The third tool, `find_and_save_book`, joins those two steps for a user who
explicitly asks for both. It uses the same search and save methods, so there is
only one implementation of each operation to maintain. Three tools felt enough
for this version: each has a clear role, and the combined tool makes a common
request convenient. For everyday use, though, I would also want to view the
saved list and remove books from it.

The most important decision was what to do when a search returned several
books. A query such as "machine learning" is too broad to justify choosing one
automatically, so the combined tool returns the candidates without saving.
Its `steps` field shows whether the save step actually ran. Repeating a save
was another case worth checking; the database's primary key prevents duplicate
entries even after restarting the server. Testing also exposed a problem beyond
the tool logic: an HTTP connection was reused after its event loop had closed.
Giving each test its own API client resolved that issue. All seven scenarios
then passed with the real model, including duplicate saves, ambiguous requests,
and books or IDs missing from the catalog. This showed why checking the Python
functions alone was not enough. I would
improve the search and expand the catalog next, since eight seeded books are
useful for a repeatable demonstration but limited as a research assistant.
