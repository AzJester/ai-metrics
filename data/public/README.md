# data/public/

CSV exports committed here are loaded into the warehouse when the hosted
dashboard boots (Streamlit Community Cloud rebuilds its filesystem on every
deploy, so the data has to live in the repo).

Use the same filename prefixes and columns as `data/drop/` (see the README
table): `chatgpt_*.csv`, `claude_*.csv`, `rovo_*.csv`, `pwin_*.csv`,
`icertis_*.csv`, `copilot_*.csv`, `roster_*.csv`, `survey_*.csv`.

After adding or updating files, push to the branch the app deploys from;
Streamlit Cloud redeploys automatically on push.

**These files are world-readable once the app's repo or URL is shared.**
Only commit exports here because this usage data has been deemed
non-confidential. If that decision ever changes, move the files back to the
gitignored `data/drop/` flow and restrict the app's viewers in its Streamlit
Cloud sharing settings.
