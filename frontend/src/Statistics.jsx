import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

const PAGE_SIZES = [10, 25, 50, 100]
const GRAPH_DOTS = 500
const WINDOWS = [
  { id: 'day', label: 'Day' },
  { id: 'week', label: 'Week' },
  { id: 'month', label: 'Month' },
]

function utcDay(date) {
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`
}

function defaultRange() {
  const end = new Date()
  const start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000)
  return { from: utcDay(start), to: utcDay(end) }
}

function formatUtc(iso) {
  if (!iso) {
    return ''
  }
  const date = new Date(iso)
  const pad = (value) => String(value).padStart(2, '0')
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`
}

function formatDuration(seconds) {
  const whole = Math.max(0, Number(seconds) || 0)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const secs = whole % 60
  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`
  }
  return `${secs}s`
}

function formatPercent(value) {
  if (value == null) {
    return '—'
  }
  return `${value}%`
}

function formatAverage(value) {
  if (value == null) {
    return '—'
  }
  return `${value} ms`
}

function groupText(group) {
  if (group.status == null || String(group.status) === group.message) {
    return group.message
  }
  return `${group.status} ${group.message}`
}

function ResponseChart({ graph }) {
  const maxMs = graph?.max_ms ?? 1000
  const points = graph?.points ?? []
  const width = GRAPH_DOTS
  const top = 8
  const bottom = 148
  const height = 160
  const xFor = (slot) => (slot / (GRAPH_DOTS - 1)) * (width - 1)
  const yFor = (ms) => bottom - (Math.min(ms, maxMs) / maxMs) * (bottom - top)
  const segments = []
  let current = []
  for (const point of points) {
    const xy = [xFor(point.slot), yFor(point.ms)]
    if (!point.connect && current.length) {
      segments.push(current)
      current = []
    }
    current.push(xy)
  }
  if (current.length) {
    segments.push(current)
  }
  return (
    <svg className="chart" width={width} height={height} role="img" aria-label="Response time in milliseconds">
      <line x1="0" y1={bottom} x2={width} y2={bottom} stroke="#ccc" />
      <line x1="0" y1={top} x2={width} y2={top} stroke="#eee" />
      {segments.map((segment, index) =>
        segment.length > 1 ? (
          <polyline
            key={index}
            fill="none"
            stroke="#1a73e8"
            strokeWidth="1"
            points={segment.map(([x, y]) => `${x},${y}`).join(' ')}
          />
        ) : null,
      )}
      {points.map((point) => (
        <circle key={point.slot} cx={xFor(point.slot)} cy={yFor(point.ms)} r="1.5" fill="#1a73e8" />
      ))}
    </svg>
  )
}

export default function Statistics({ entry, token, onAuthRequired, onSignedOut }) {
  const initialRange = defaultRange()
  const [windowName, setWindowName] = useState('day')
  const [from, setFrom] = useState(initialRange.from)
  const [to, setTo] = useState(initialRange.to)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [report, setReport] = useState(null)
  const [popup, setPopup] = useState(null)
  const generation = useRef(0)
  const mounted = useRef(true)
  const query = useRef({})
  query.current = { token, windowName, from, to, page, pageSize, entryId: entry.id }

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (!token) {
      onAuthRequired()
    }
  }, [token])

  async function load() {
    const current = query.current
    if (!current.token || !current.from || !current.to) {
      return
    }
    const seen = ++generation.current
    const params = new URLSearchParams({
      id: String(current.entryId),
      window: current.windowName,
      from: current.from,
      to: current.to,
      page: String(current.page),
      page_size: String(current.pageSize),
    })
    try {
      const data = await api(`/api/stats?${params}`, { token: current.token })
      if (!mounted.current || seen !== generation.current) {
        return
      }
      setReport(data)
      setPage((value) => (value === data.page ? value : data.page))
      setPageSize((value) => (value === data.page_size ? value : data.page_size))
    } catch (error) {
      if (!mounted.current || seen !== generation.current) {
        return
      }
      if (error?.code === 'token_expired') {
        onSignedOut()
        onAuthRequired()
        return
      }
      setPopup({ kind: 'error', message: error.message || 'Request failed.' })
    }
  }

  async function pollNow() {
    const current = query.current
    if (!current.token) {
      onAuthRequired()
      return
    }
    const timeoutSeconds = Number(entry.timeoutSeconds) || 5
    try {
      await api('/api/entries/poll', {
        method: 'POST',
        token: current.token,
        body: { id: current.entryId },
        timeoutMs: (timeoutSeconds * 2 + 5) * 1000,
      })
      if (!mounted.current) {
        return
      }
      await load()
    } catch (error) {
      if (!mounted.current) {
        return
      }
      if (error?.code === 'token_expired') {
        onSignedOut()
        onAuthRequired()
        return
      }
      setPopup({ kind: 'error', message: error.message || 'Request failed.' })
    }
  }

  useEffect(() => {
    if (!token) {
      return undefined
    }
    load()
    if (!autoRefresh) {
      return undefined
    }
    const timer = setInterval(load, 10000)
    return () => clearInterval(timer)
  }, [token, autoRefresh, windowName, from, to, page, pageSize, entry.id])

  const shown = token ? report : null
  const total = shown?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize) || 1)
  const rows = shown?.rows ?? []

  return (
    <section>
      <h1 className="stats-url" title={entry.url}>
        {entry.url}
      </h1>
      <div className="stats-controls">
        {WINDOWS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={windowName === item.id}
            onClick={() => {
              setWindowName(item.id)
              setPage(1)
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <p>
        Successful checks: {formatPercent(shown?.percentage)} Average response time:{' '}
        {formatAverage(shown?.average_ms)}
      </p>
      <p>Response time, 0–{shown?.graph?.max_ms ?? 1000} ms</p>
      <ResponseChart graph={shown?.graph} />
      <div className="stats-controls">
        <label>
          From (UTC){' '}
          <input
            type="date"
            value={from}
            onChange={(event) => {
              setFrom(event.target.value)
              setPage(1)
            }}
          />
        </label>{' '}
        <label>
          To (UTC){' '}
          <input
            type="date"
            value={to}
            onChange={(event) => {
              setTo(event.target.value)
              setPage(1)
            }}
          />
        </label>
      </div>
      <table>
        <thead>
          <tr>
            <th>Type</th>
            <th>Start (UTC)</th>
            <th>End (UTC)</th>
            <th>Duration</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={5}>{shown ? 'No incidents in this range.' : ''}</td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr
                key={`${row.kind}-${row.start}-${index}`}
                className={row.kind === 'incident' ? 'incident' : undefined}
                onClick={
                  row.kind === 'incident' ? () => setPopup({ kind: 'incident', row }) : undefined
                }
              >
                <td>{row.kind === 'incident' ? 'Incident' : 'No data'}</td>
                <td>{formatUtc(row.start)}</td>
                <td>{formatUtc(row.end)}</td>
                <td>{formatDuration(row.duration_seconds)}</td>
                <td>{row.reason}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      <div className="pager">
        <label>
          Page size{' '}
          <select
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value))
              setPage(1)
            }}
          >
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
        <button
          type="button"
          onClick={() => setPage((current) => current + 1)}
          disabled={page >= pageCount}
        >
          Next
        </button>
      </div>
      <div className="stats-controls">
        <button type="button" onClick={load}>
          Refresh
        </button>{' '}
        <label>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(event) => setAutoRefresh(event.target.checked)}
          />{' '}
          Refresh every 10 seconds
        </label>
      </div>
      <p>Last poll (UTC): {formatUtc(shown?.last_polled_at) || 'not polled yet'}</p>
      <div className="stats-controls">
        <button type="button" onClick={pollNow}>
          Poll now
        </button>
      </div>
      {popup?.kind === 'error' ? (
        <div className="popup-backdrop">
          <div className="popup" role="dialog">
            <p>{popup.message}</p>
            <button type="button" onClick={() => setPopup(null)}>
              OK
            </button>
          </div>
        </div>
      ) : null}
      {popup?.kind === 'incident' ? (
        <div className="popup-backdrop">
          <div className="popup" role="dialog">
            <p>Errors in this incident</p>
            <ul>
              {popup.row.groups.map((group) => (
                <li key={`${group.status}-${group.message}`}>
                  {groupText(group)} × {group.count}
                </li>
              ))}
            </ul>
            <button type="button" onClick={() => setPopup(null)}>
              Close
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
