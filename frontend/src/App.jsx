import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import Groups from './Groups.jsx'
import Statistics from './Statistics.jsx'

const PAGE_SIZES = [10, 25, 50, 100]
const REFRESH_MS = 5000
const SESSION_KEY = 'monitorSession'
const BLANK_START = { url: '', interval: '30', timeout: '5', expectedCode: '200' }
const FIELD_LIMITS = {
  interval_seconds: { min: 30, max: 3600, label: 'Polling rate' },
  timeout_seconds: { min: 1, max: null, label: 'Timeout' },
  expected_code: { min: 100, max: 599, label: 'Expected code' },
}

function readSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    if (!raw) {
      return { token: '', username: '' }
    }
    const parsed = JSON.parse(raw)
    if (typeof parsed?.token !== 'string' || typeof parsed?.username !== 'string') {
      return { token: '', username: '' }
    }
    if (!parsed.token || !parsed.username) {
      return { token: '', username: '' }
    }
    return { token: parsed.token, username: parsed.username }
  } catch {
    return { token: '', username: '' }
  }
}

function formatUtc(iso) {
  if (!iso) {
    return ''
  }
  const date = new Date(iso)
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`
}

function nextPollTitle(iso) {
  if (!iso) {
    return 'Next poll: not polled yet'
  }
  return `Next poll: ${formatUtc(iso)}`
}

function displayUrl(url) {
  return url.length > 20 ? url.slice(0, 20) : url
}

function parseSeconds(text) {
  if (!/^[1-9]\d*$/.test(String(text).trim())) {
    return null
  }
  return Number(String(text).trim())
}

function parseBounded(text, min, max) {
  const parsed = parseSeconds(text)
  if (parsed == null || parsed < min || parsed > max) {
    return null
  }
  return parsed
}

function parseField(field, text) {
  const limit = FIELD_LIMITS[field]
  if (limit.max == null) {
    return parseSeconds(text)
  }
  return parseBounded(text, limit.min, limit.max)
}

function fieldError(field) {
  const limit = FIELD_LIMITS[field]
  if (limit.max == null) {
    return `${limit.label} must be an integer of at least 1.`
  }
  return `${limit.label} must be an integer from ${limit.min} to ${limit.max}.`
}

function withField(entry, field, parsed) {
  return {
    interval: field === 'interval_seconds' ? parsed : entry.interval_seconds,
    timeout: field === 'timeout_seconds' ? parsed : entry.timeout_seconds,
    expectedCode: field === 'expected_code' ? parsed : entry.expected_code ?? 200,
  }
}

export default function App() {
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [entries, setEntries] = useState([])
  const [token, setToken] = useState(() => readSession().token)
  const [username, setUsername] = useState(() => readSession().username)
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')
  const [blank, setBlank] = useState(BLANK_START)
  const [popup, setPopup] = useState(null)
  const [loginUser, setLoginUser] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [statsEntry, setStatsEntry] = useState(null)
  const [view, setView] = useState('urls')
  const [groupOptions, setGroupOptions] = useState([])

  const pendingEdit = useRef(0)
  const skipCommit = useRef(false)
  const skipBlank = useRef(false)
  const blankOrigin = useRef('')
  const creating = useRef(false)
  const generation = useRef(0)
  const blankRef = useRef(blank)
  const entriesRef = useRef(entries)
  const draftRef = useRef(draft)
  const session = useRef({ token: '', page: 1, pageSize: 10 })
  const groupsRef = useRef(groupOptions)
  blankRef.current = blank
  entriesRef.current = entries
  draftRef.current = draft
  session.current = { token, page, pageSize }
  groupsRef.current = groupOptions

  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const signedIn = Boolean(token)

  useEffect(() => {
    if (token && username) {
      localStorage.setItem(SESSION_KEY, JSON.stringify({ token, username }))
      return
    }
    localStorage.removeItem(SESSION_KEY)
  }, [token, username])

  function applyPage(data) {
    setEntries(data.entries)
    setTotal(data.total)
    setPage(data.page)
    setPageSize(data.page_size)
  }

  function showRequestError(error) {
    if (error?.code === 'token_expired') {
      setToken('')
      setUsername('')
      setEditing(null)
      setPopup({ kind: 'expired' })
      return
    }
    setPopup((current) => {
      if (current?.kind === 'signin' || current?.kind === 'expired') {
        return current
      }
      if (current?.kind === 'error' && current.message === error.message) {
        return current
      }
      return { kind: 'error', message: error.message || 'Request failed.' }
    })
  }

  useEffect(() => {
    let active = true

    async function load() {
      const seen = generation.current
      try {
        const data = await api(`/api/entries?page=${page}&page_size=${pageSize}`)
        if (!active || seen !== generation.current) {
          return
        }
        applyPage(data)
      } catch (error) {
        if (!active || seen !== generation.current) {
          return
        }
        showRequestError(error)
      }
    }

    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [page, pageSize])

  useEffect(() => {
    function applyHash() {
      const wantsGroups = window.location.hash === '#groups'
      if (wantsGroups && !session.current.token) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search)
        setView('urls')
        return
      }
      if (wantsGroups) {
        setStatsEntry(null)
      }
      setView(wantsGroups ? 'groups' : 'urls')
    }

    applyHash()
    window.addEventListener('hashchange', applyHash)
    return () => window.removeEventListener('hashchange', applyHash)
  }, [token])

  useEffect(() => {
    if (!token) {
      setGroupOptions([])
      return
    }
    let active = true

    async function load() {
      try {
        const data = await api('/api/groups', { token: session.current.token })
        if (active) {
          setGroupOptions(data.groups)
        }
      } catch (error) {
        if (active) {
          showRequestError(error)
        }
      }
    }

    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [token])

  function nextPollState(status, groupId) {
    if (status !== 'ACTIVE') {
      return 'URL_PAUSED'
    }
    const group = groupsRef.current.find((item) => item.id === groupId)
    if (group?.paused) {
      return 'GROUP_PAUSED'
    }
    return 'ACTIVE'
  }

  async function assignGroup(entry, raw) {
    const groupId = raw === '' ? null : Number(raw)
    const previous = entriesRef.current
    setEntries(
      previous.map((item) =>
        item.id === entry.id
          ? { ...item, group_id: groupId, poll_state: nextPollState(item.status, groupId) }
          : item,
      ),
    )
    generation.current += 1
    try {
      const data = await api('/api/entries/group', {
        method: 'POST',
        token: session.current.token,
        body: {
          url: entry.url,
          group_id: groupId,
          page: session.current.page,
          page_size: session.current.pageSize,
        },
      })
      generation.current += 1
      applyPage(data)
    } catch (error) {
      generation.current += 1
      setEntries(previous)
      showRequestError(error)
    }
  }

  async function sendUpdate(entry, interval, timeout, expectedCode, status) {
    const mine = ++pendingEdit.current
    generation.current += 1
    try {
      const data = await api('/api/entries', {
        method: 'PATCH',
        token: session.current.token,
        body: {
          url: entry.url,
          interval_seconds: interval,
          timeout_seconds: timeout,
          expected_code: expectedCode,
          status,
          page: session.current.page,
          page_size: session.current.pageSize,
        },
      })
      if (mine !== pendingEdit.current) {
        return
      }
      generation.current += 1
      applyPage(data)
    } catch (error) {
      if (mine !== pendingEdit.current) {
        return
      }
      generation.current += 1
      showRequestError(error)
    }
  }

  async function commitField(entry, field) {
    if (skipCommit.current) {
      skipCommit.current = false
      setEditing(null)
      return
    }
    const parsed = parseField(field, draftRef.current)
    setEditing(null)
    if (parsed == null) {
      setPopup({ kind: 'error', message: fieldError(field) })
      return
    }
    if (parsed === entry[field]) {
      return
    }
    const next = withField(entry, field, parsed)
    await sendUpdate(entry, next.interval, next.timeout, next.expectedCode, entry.status)
  }

  function changeBounded(entry, field, raw) {
    draftRef.current = raw
    setEditing({ id: entry.id, field })
    setDraft(raw)
    const parsed = parseField(field, raw)
    if (parsed == null || parsed === entry[field]) {
      return
    }
    const next = withField(entry, field, parsed)
    sendUpdate(entry, next.interval, next.timeout, next.expectedCode, entry.status)
  }

  function beginEdit(entry, field) {
    setEditing({ id: entry.id, field })
    setDraft(String(entry[field]))
  }

  function onEditKeyDown(event) {
    if (event.key !== 'Escape') {
      return
    }
    skipCommit.current = true
    setEditing(null)
    event.currentTarget.blur()
  }

  function focusedCommit() {
    const active = document.activeElement
    if (!(active instanceof HTMLElement) || !active.dataset.commit) {
      return null
    }
    return {
      commit: active.dataset.commit,
      field: active.dataset.field || '',
      entryId: Number(active.dataset.entryId || 0),
    }
  }

  function releaseFocus() {
    const active = document.activeElement
    if (!(active instanceof HTMLElement) || !active.dataset.commit) {
      setEditing(null)
      return
    }
    if (active.dataset.commit === 'entry') {
      skipCommit.current = true
    } else {
      skipBlank.current = true
    }
    setEditing(null)
    active.blur()
  }

  async function saveOtherEntry(focus, draftText) {
    const entry = entriesRef.current.find((item) => item.id === focus.entryId)
    if (!entry) {
      return true
    }
    const parsed = parseField(focus.field, draftText)
    if (parsed == null) {
      setPopup({ kind: 'error', message: fieldError(focus.field) })
      return false
    }
    if (parsed === entry[focus.field]) {
      return true
    }
    const next = withField(entry, focus.field, parsed)
    await sendUpdate(entry, next.interval, next.timeout, next.expectedCode, entry.status)
    return true
  }

  async function toggle(entry) {
    const focus = focusedCommit()
    const draftText = draftRef.current
    releaseFocus()
    if (focus?.commit === 'blank' && focus.field === 'url') {
      await createEntry()
    }
    if (focus?.commit === 'entry' && focus.entryId !== entry.id) {
      const saved = await saveOtherEntry(focus, draftText)
      if (!saved) {
        return
      }
    }
    let interval = entry.interval_seconds
    let timeout = entry.timeout_seconds
    let expectedCode = entry.expected_code ?? 200
    if (focus?.commit === 'entry' && focus.entryId === entry.id) {
      const parsed = parseField(focus.field, draftText)
      if (parsed == null) {
        setPopup({ kind: 'error', message: fieldError(focus.field) })
        return
      }
      const next = withField(entry, focus.field, parsed)
      interval = next.interval
      timeout = next.timeout
      expectedCode = next.expectedCode
    }
    const status = entry.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'
    await sendUpdate(entry, interval, timeout, expectedCode, status)
  }

  async function remove(entry) {
    const focus = focusedCommit()
    const draftText = draftRef.current
    releaseFocus()
    if (focus?.commit === 'blank' && focus.field === 'url') {
      await createEntry()
    }
    if (focus?.commit === 'entry' && focus.entryId !== entry.id) {
      const saved = await saveOtherEntry(focus, draftText)
      if (!saved) {
        return
      }
    }
    generation.current += 1
    try {
      const data = await api('/api/entries/delete', {
        method: 'POST',
        token: session.current.token,
        body: {
          url: entry.url,
          page: session.current.page,
          page_size: session.current.pageSize,
        },
      })
      generation.current += 1
      applyPage(data)
    } catch (error) {
      generation.current += 1
      showRequestError(error)
    }
  }

  async function createEntry() {
    if (creating.current) {
      return
    }
    const current = blankRef.current
    const url = current.url.trim()
    if (!url) {
      return
    }
    const interval = parseBounded(current.interval, 30, 3600)
    const timeout = parseSeconds(current.timeout)
    const expectedCode = parseBounded(current.expectedCode, 100, 599)
    if (interval == null || timeout == null || expectedCode == null) {
      setPopup({
        kind: 'error',
        message:
          'Polling rate must be from 30 to 3600, timeout at least 1, and expected code from 100 to 599.',
      })
      return
    }
    creating.current = true
    generation.current += 1
    try {
      const data = await api('/api/entries', {
        method: 'POST',
        token: session.current.token,
        body: {
          url,
          interval_seconds: interval,
          timeout_seconds: timeout,
          expected_code: expectedCode,
          page: session.current.page,
          page_size: session.current.pageSize,
        },
      })
      generation.current += 1
      setBlank(BLANK_START)
      applyPage(data)
    } catch (error) {
      generation.current += 1
      showRequestError(error)
    } finally {
      creating.current = false
    }
  }

  function blurBlankUrl() {
    if (skipBlank.current) {
      skipBlank.current = false
      return
    }
    createEntry()
  }

  function blurBlankNumber(field) {
    if (skipBlank.current) {
      skipBlank.current = false
      return
    }
    const blankFields = {
      interval: 'interval_seconds',
      timeout: 'timeout_seconds',
      expectedCode: 'expected_code',
    }
    const entryField = blankFields[field]
    if (parseField(entryField, blankRef.current[field]) != null) {
      return
    }
    setBlank((current) => ({ ...current, [field]: blankOrigin.current }))
    setPopup({ kind: 'error', message: fieldError(entryField) })
  }

  function keyBlank(event, field) {
    if (event.key !== 'Escape') {
      return
    }
    skipBlank.current = true
    setBlank((current) => ({ ...current, [field]: blankOrigin.current }))
    event.currentTarget.blur()
  }

  function focusBlank(field) {
    blankOrigin.current = blankRef.current[field]
  }

  async function submitLogin(event) {
    event.preventDefault()
    try {
      const result = await api('/api/login', {
        method: 'POST',
        body: { username: loginUser, password: loginPassword },
      })
      setToken(result.token)
      setUsername(result.username)
      setLoginPassword('')
      setPopup(null)
    } catch (error) {
      setLoginPassword('')
      setToken('')
      setUsername('')
      setPopup({ kind: 'error', message: error.message })
    }
  }

  function logout() {
    setToken('')
    setUsername('')
    setEditing(null)
    setPopup(null)
    if (window.location.hash === '#groups') {
      window.location.hash = ''
    }
  }

  function requireSignIn() {
    setPopup({ kind: 'signin', lead: 'Please Sign in' })
  }

  async function openStats(entry) {
    const focus = focusedCommit()
    const draftText = draftRef.current
    releaseFocus()
    if (focus?.commit === 'blank' && focus.field === 'url') {
      await createEntry()
    }
    if (focus?.commit === 'entry') {
      const saved = await saveOtherEntry(focus, draftText)
      if (!saved) {
        return
      }
    }
    setStatsEntry({ id: entry.id, url: entry.url, timeoutSeconds: entry.timeout_seconds })
  }

  function changePageSize(event) {
    setPageSize(Number(event.target.value))
    setPage(1)
  }

  function secondsInput(entry, field) {
    const focused = editing && editing.id === entry.id && editing.field === field
    return (
      <input
        type="text"
        inputMode="numeric"
        data-commit="entry"
        data-field={field}
        data-entry-id={entry.id}
        aria-label={`${FIELD_LIMITS[field].label} for ${entry.url}`}
        value={focused ? draft : String(entry[field])}
        onFocus={() => beginEdit(entry, field)}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => commitField(entry, field)}
        onKeyDown={onEditKeyDown}
      />
    )
  }

  function boundedInput(entry, field) {
    const limit = FIELD_LIMITS[field]
    const focused = editing && editing.id === entry.id && editing.field === field
    return (
      <input
        type="number"
        min={limit.min}
        max={limit.max}
        step={1}
        data-commit="entry"
        data-field={field}
        data-entry-id={entry.id}
        aria-label={`${limit.label} for ${entry.url}`}
        value={focused ? draft : String(entry[field])}
        onFocus={() => beginEdit(entry, field)}
        onChange={(event) => changeBounded(entry, field, event.target.value)}
        onBlur={() => commitField(entry, field)}
        onKeyDown={onEditKeyDown}
      />
    )
  }

  return (
    <>
      <header className="top">
        <div>
          {view === 'groups' && signedIn ? (
            <button type="button" onClick={() => { window.location.hash = '' }}>
              URLs
            </button>
          ) : null}
          {signedIn && view !== 'groups' && !statsEntry ? <a href="#groups">Groups</a> : null}
          {statsEntry ? (
            <button type="button" onClick={() => setStatsEntry(null)}>
              Return to main
            </button>
          ) : null}
        </div>
        <div>
          {signedIn ? (
            <>
              <span>Signed in as {username}</span>{' '}
              <button type="button" onClick={logout}>
                Logout
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setPopup({ kind: 'signin' })}>
              Sign In
            </button>
          )}
        </div>
      </header>
      {view === 'groups' && signedIn ? <Groups token={token} onError={showRequestError} /> : null}
      {view !== 'groups' && statsEntry ? (
        <Statistics
          entry={statsEntry}
          token={token}
          onAuthRequired={requireSignIn}
          onSignedOut={logout}
        />
      ) : null}
      {view !== 'groups' && !statsEntry ? (
      <>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>URL</th>
            <th>Polling rate (seconds)</th>
            <th>Timeout (seconds)</th>
            <th>Expected code</th>
            <th>Play / pause</th>
            <th>Status</th>
            <th>Error</th>
            <th>Last poll (UTC)</th>
            {signedIn ? <th>Group</th> : null}
            {signedIn ? <th>Delete</th> : null}
            {signedIn ? <th>Statistics</th> : null}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td>{entry.id}</td>
              <td title={entry.url}>{displayUrl(entry.url)}</td>
              <td>{signedIn ? boundedInput(entry, 'interval_seconds') : entry.interval_seconds}</td>
              <td>{signedIn ? secondsInput(entry, 'timeout_seconds') : entry.timeout_seconds}</td>
              <td>{signedIn ? boundedInput(entry, 'expected_code') : entry.expected_code}</td>
              <td>
                {signedIn ? (
                  <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => toggle(entry)}>
                    {entry.status === 'ACTIVE' ? 'Pause' : 'Play'}
                  </button>
                ) : null}
                {signedIn ? ' ' : null}
                {entry.poll_state}
              </td>
              <td>{entry.health}</td>
              <td>{entry.error}</td>
              <td title={nextPollTitle(entry.next_poll_at)}>{formatUtc(entry.last_polled_at)}</td>
              {signedIn ? (
                <td>
                  <select
                    aria-label={`Group for ${entry.url}`}
                    value={entry.group_id == null ? '' : String(entry.group_id)}
                    onChange={(event) => assignGroup(entry, event.target.value)}
                  >
                    <option value="">NONE</option>
                    {groupOptions.map((group) => (
                      <option key={group.id} value={String(group.id)}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                </td>
              ) : null}
              {signedIn ? (
                <td>
                  <button
                    type="button"
                    title="Delete entry"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => remove(entry)}
                  >
                    [X]
                  </button>
                </td>
              ) : null}
              {signedIn ? (
                <td>
                  <button
                    type="button"
                    title="Statistics"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => openStats(entry)}
                  >
                    [i]
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
          {signedIn ? (
            <tr>
              <td />
              <td>
                <input
                  type="text"
                  value={blank.url}
                  aria-label="New URL"
                  data-commit="blank"
                  data-field="url"
                  onFocus={() => focusBlank('url')}
                  onChange={(event) => setBlank((current) => ({ ...current, url: event.target.value }))}
                  onBlur={blurBlankUrl}
                  onKeyDown={(event) => keyBlank(event, 'url')}
                />
              </td>
              <td>
                <input
                  type="number"
                  min={30}
                  max={3600}
                  step={1}
                  value={blank.interval}
                  aria-label="New polling rate"
                  data-commit="blank"
                  data-field="interval"
                  onFocus={() => focusBlank('interval')}
                  onChange={(event) => setBlank((current) => ({ ...current, interval: event.target.value }))}
                  onBlur={() => blurBlankNumber('interval')}
                  onKeyDown={(event) => keyBlank(event, 'interval')}
                />
              </td>
              <td>
                <input
                  type="text"
                  inputMode="numeric"
                  value={blank.timeout}
                  aria-label="New timeout"
                  data-commit="blank"
                  data-field="timeout"
                  onFocus={() => focusBlank('timeout')}
                  onChange={(event) => setBlank((current) => ({ ...current, timeout: event.target.value }))}
                  onBlur={() => blurBlankNumber('timeout')}
                  onKeyDown={(event) => keyBlank(event, 'timeout')}
                />
              </td>
              <td>
                <input
                  type="number"
                  min={100}
                  max={599}
                  step={1}
                  value={blank.expectedCode}
                  aria-label="New expected code"
                  data-commit="blank"
                  data-field="expectedCode"
                  onFocus={() => focusBlank('expectedCode')}
                  onChange={(event) => setBlank((current) => ({ ...current, expectedCode: event.target.value }))}
                  onBlur={() => blurBlankNumber('expectedCode')}
                  onKeyDown={(event) => keyBlank(event, 'expectedCode')}
                />
              </td>
              <td>URL_PAUSED</td>
              <td />
              <td />
              <td />
              <td />
              <td />
              <td />
            </tr>
          ) : null}
        </tbody>
      </table>
      <div className="pager">
        <label>
          Page size{' '}
          <select value={pageSize} onChange={changePageSize}>
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>{' '}
        <button type="button" onClick={() => setPage((current) => current - 1)} disabled={page <= 1}>
          Previous
        </button>{' '}
        <span>
          Page {Math.min(page, pageCount)} of {pageCount}
        </span>{' '}
        <button type="button" onClick={() => setPage((current) => current + 1)} disabled={page >= pageCount}>
          Next
        </button>
      </div>
      </>
      ) : null}
      {popup ? (
        <div className="popup-backdrop">
          <div className="popup" role="dialog">
            {popup.kind === 'expired' ? (
              <>
                <p>Please sign in again</p>
                <button type="button" onClick={() => setPopup({ kind: 'signin' })}>
                  Sign in
                </button>{' '}
                <button type="button" onClick={() => setPopup(null)}>
                  Close
                </button>
              </>
            ) : null}
            {popup.kind === 'error' ? (
              <>
                <p>{popup.message}</p>
                <button type="button" onClick={() => setPopup(null)}>
                  OK
                </button>
              </>
            ) : null}
            {popup.kind === 'signin' ? (
              <form onSubmit={submitLogin}>
                {popup.lead ? <p>{popup.lead}</p> : null}
                <label>
                  Username{' '}
                  <input
                    value={loginUser}
                    autoComplete="username"
                    onChange={(event) => setLoginUser(event.target.value)}
                  />
                </label>
                <label>
                  Password{' '}
                  <input
                    type="password"
                    value={loginPassword}
                    autoComplete="current-password"
                    onChange={(event) => setLoginPassword(event.target.value)}
                  />
                </label>
                <div className="popup-actions">
                  <button type="submit">Sign in</button>{' '}
                  <button type="button" onClick={() => setPopup(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  )
}
