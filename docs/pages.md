# Pages

The URL list reloads every 5 seconds. Groups, Maintenances, and Mailing do the same. Times on screen are UTC.

A guest sees the URL list. Groups, Maintenances, Mailing, and Statistics stay behind sign-in. Opening those addresses as a guest returns to the URL list.

## Header

Shown on every page.

- **Sign In** (guest): opens the sign-in popup.
- **Signed in as {name}**: the current account.
- **Logout**: ends the session in this browser.
- **URLs**: back to the URL list. Shown when another page is open.
- **Groups**: group list. Signed-in only.
- **Maintenances**: maintenance windows. Signed-in only.
- **Mailing**: stored messages. Signed-in only.
- **Return to main**: leaves Statistics and shows the URL list again.

## Popups used on more than one page

- **Sign in**: username and password. **Sign in** sends them. **Cancel** closes the popup. Wrong credentials show an error and leave the page in guest mode. A fresh install accepts `admin` / `admin`. The token lasts one hour and stays after a reload.
- **Please sign in again**: the token expired. **Sign in** opens the sign-in popup. **Close** dismisses this one.
- **Please Sign in**: same sign-in popup, shown when Statistics is opened without a session.
- **Error**: the message from the failed action, and **OK**.

## URLs

The main table.

| Column | What it is |
| --- | --- |
| ID | Row id. |
| URL | First 20 characters. The hint is the full address. |
| Polling rate (seconds) | How often this URL is checked. 30–3600. |
| Timeout (seconds) | How long one request may take. At least 1. |
| Expected code | HTTP status that counts as success. 100–599. Default 200. |
| Play / pause | Pause switch and the pause state. |
| Status | `UP` or `DOWN` from the latest saved check. Empty if this URL has not been checked. |
| Error | Latest error text. Empty when the latest check was OK. |
| Last poll (UTC) | Time of the latest saved check. The hint is the next poll time. |
| Group | Which group this URL belongs to. Signed-in only. |
| Delete | Removes the row from the list. Signed-in only. |
| Statistics | Opens Statistics. Signed-in only. |

Pause state is `ACTIVE`, `URL_PAUSED`, or `GROUP_PAUSED`. A URL is checked only when it is `ACTIVE`. `URL_PAUSED` is this row's own pause. `GROUP_PAUSED` means the group is paused and this row is not.

Signed-in controls:

- **Pause** / **Play**: pause or resume this URL. Does not change the group pause.
- **Group** dropdown: `NONE` or a group name. Guests do not see the column.
- **[X]**: hide this URL. History stays. Adding the same address again restores the row. Hint: "Delete entry".
- **[i]**: open Statistics for this URL. Hint: "Statistics".
- Number fields: edit in place. Leaving the field saves. Escape cancels. A bad value opens the error popup.
- Empty row under the list: type a URL, rate, timeout, and expected code, then leave the field. That creates the URL in the paused state. The address must use `http` or `https`, or start with `www` or `localhost`. A port is allowed. A slash that is the whole path is removed. A slash after a page path stays.

Guests see the same facts and cannot edit, pause, assign a group, delete, or open Statistics.

**Page size**, **Previous**, **Next**: 10, 25, 50, or 100 rows.

## Groups

Signed-in only. `#groups`.

| Column | What it is |
| --- | --- |
| ID | Group id. |
| Name | Editable. At most 50 characters. Empty and duplicate names are rejected. |
| URLs | How many URLs are in the group. Deleted URLs are not counted. |
| Play / pause | **Pause** or **Play** for the whole group. |
| Health | `UP`, `DOWN`, or `NO_DATA_YET`. `UP` and `DOWN` are used only while the response status is `POLLING`. `DOWN` means at least one URL that is still being checked is down. Paused URLs are skipped. |
| Status | `EMPTY` (no URLs), `URLS_PAUSED` (every URL is paused; this wins over a group pause), `GROUP_PAUSED`, `POLLING`, or `ERROR`. |
| Delete | **[X]**. Deletes the group and sets its URLs to `NONE`. Hint: "Delete group". |
| Email | **[M]**. Opens the email popup. Hint: "Email addresses". |

The empty name field under the list creates a group when you leave the field. A new group is not paused.

Email popup, "Email addresses for {name}":

- Each row is one address. Edit it and leave the field to save. **[X]** removes that address. Hint: "Delete email".
- The empty field adds an address when you leave it.
- **Close** saves a focused edit, then closes the popup.

These addresses are the recipients for that group's URLs. No message is stored when the group has none.

## Maintenances

Signed-in only. `#maintenances`. Two tables: **URL maintenances** and **Group maintenances**. Checks keep running during a window. Mail for a covered edge is held until the window ends. Overlapping windows for the same URL count as one stretch.

Each table:

| Column | What it is |
| --- | --- |
| URL or Group | Dropdown of current URLs or groups. |
| Start (UTC) | Window start. |
| End (UTC) | Window end. |
| Status | `NOT_STARTED`, `STARTED_AND_UP`, `STARTED_AND_DOWN`, or `ENDED`. `STARTED_AND_DOWN` means at least one check in the window was down. |
| Delete | **[X]**. Removes the window. Hint: "Delete maintenance". Ending it this way follows the same mail rules as a window that reached its end time. |

The empty row starts as `NONE`. Choosing a URL or a group creates the window. The default start is one hour from now, and the default end is two hours from now. Each table has **Page size**, **Previous**, and **Next** (10, 25, 50, 100).

## Mailing

Signed-in only. `#mailing`. Heading **Sent emails**. This is a local stand-in for a mailbox. Nothing is sent over SMTP.

| Column | What it is |
| --- | --- |
| To | Addresses of the group that owned the URL. |
| Message | "… downtime incident started at …" or "… downtime incident ended. It was started at … and ended at …". |

A message is stored when an incident starts and when it ends, and only if that URL is in a group that has addresses. Checks inside the incident do not add messages. A window that covers an edge holds that message until the window ends. An incident that both starts and ends inside a window is not stored. If there are no rows, the page says "No emails yet." There are no buttons on this page.

## Statistics

Signed-in only. Opened with **[i]** on a URL. The title is the full URL.

- **Day**, **Week**, **Month**: success share and average response time for the last 24 hours, 7 days, or 30 days. Day is the default. The percentage counts every check, including a single failure.
- Line chart: "Last 100 checks, 0–{max} ms". Response time of checks that returned an HTTP status. Timeouts are left off the line. The line breaks across an incident or a gap. The scale starts at 1000 ms and grows if a point is higher.
- **From (UTC)** and **To (UTC)**: date range for the incident log. The default is the last 30 days.
- Incident table: **Type**, **Start (UTC)**, **End (UTC)**, **Duration**, **Reason**. Type is Incident or No data. One failed check is not an incident. Two failed checks in a row are one incident, including mixed error texts. An open incident has no end time. No data is a gap, not an outage: the backend was down, polling was paused, or the entry was deactivated. Click an Incident row to open its error popup.
- **Page size**, **Previous**, **Next**: 10, 25, 50, or 100 log rows. Empty range: "No incidents in this range."
- **Refresh**: load this page again.
- **Refresh every 10 seconds**: repeat that load while the box is checked.
- Last poll time.
- "Down for …" while an incident is open, otherwise "no incidents right now".
- "Last response time: … ms", or "not polled yet".
- **Poll now**: run one check immediately and move the next scheduled check. It does not clear a URL pause or a group pause. If this URL is already waiting for a response, the error popup says "Can't request this right now. A request is already waiting for a response."

Incident popup, "Errors in this incident": one line per status and message, with a count. **Close** dismisses it.
