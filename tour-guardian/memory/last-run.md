# Tour Guardian run — 2026-10-26 22:50:10 MST

Overall: **ALL PASS** (7/7 checks passed)

| # | Check | Target | Rule | Result | Evidence |
|---|---|---|---|---|---|
| 1 | Main site | https://victoriatourandadventure.com | HTTP 200 | PASS | HTTP 200, 13670 bytes |
| 2 | App site | https://app.victoriatourandadventure.com | HTTP 200 | PASS | HTTP 200, 73397 bytes |
| 3 | App API devices.php | https://app.victoriatourandadventure.com/api/devices.php | responds, not 5xx | PASS | HTTP 400, 25 bytes |
| 4 | App API consent.php | https://app.victoriatourandadventure.com/api/consent.php | responds, not 5xx | PASS | HTTP 400, 25 bytes |
| 5 | Chat widget JS | https://app.victoriatourandadventure.com/js/vta-chat-widget-premium.js | HTTP 200 and >= 2000 bytes | PASS | HTTP 200, 44891 bytes |
| 6 | IELTS Academy site (cyrusielts.com) | https://cyrusielts.com | HTTP 200 | PASS | HTTP 200, 89150 bytes |
| 7 | IELTS Academy style.css | https://cyrusielts.com/style.css | HTTP 200 | PASS | HTTP 200, 19988 bytes |

Read-only run: GET requests only, nothing was changed.
Failures are reported to the manager; the Guardian never fixes anything itself.
