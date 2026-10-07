"""Resolve existing worksheet names without creating case-only duplicates."""


def existing_title(titles, wanted, aliases=()):
    titles = list(titles)
    if wanted in titles:
        return wanted
    candidates = {str(name).casefold() for name in (wanted, *aliases)}
    # Earlier releases used Remaining_Search for the same monthly projection.
    if wanted.casefold().startswith('remaining_'):
        candidates.add(('Remaining_Search_' + wanted[len('Remaining_'):]).casefold())
    matches = [name for name in titles if name.casefold() in candidates]
    if len(matches) > 1:
        raise ValueError(f'Multiple worksheets match {wanted}. Review their contents before publishing.')
    return matches[0] if matches else None
