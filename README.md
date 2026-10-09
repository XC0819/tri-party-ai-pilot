# slugtool（试点项目）

三方协作试点的本地小型项目，不包含任何真实业务资料。

功能：将标题转换为 URL slug，并提供 slug 截断工具。

- `slugtool.slugify.slugify(title)` — 已实现
- `slugtool.slugify.truncate_slug(slug, max_length)` — 由 TASK-20261009-001 实现

测试：`python3 -m pytest -q`（或 `python3 -m unittest discover -s tests -v`）
