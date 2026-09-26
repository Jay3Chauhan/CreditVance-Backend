# CreditVance docs

Give the Flutter developer **`FRONTEND_GUIDE.md`** in this folder. It is the full handoff: the earlier advisor, catalog, wallet, and auth work, plus home, banners, promotions, compare, search, shortlist, and wallet insights.

The same file is at the repo root as `CHANGES_AND_FRONTEND_GUIDE.md`.

| Document | Use it for |
| :--- | :--- |
| [FRONTEND_GUIDE.md](FRONTEND_GUIDE.md) | What the app should call, and what to stop hardcoding |
| [API_REFERENCE.md](API_REFERENCE.md) | Every public endpoint on one page |

Apply schema changes with `alembic upgrade head`. The current head is `c4a91e2b7f10`. Banners and promotions seed themselves the first time a public list or the home feed is requested and the table is empty.
