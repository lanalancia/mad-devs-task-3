import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

const PAGE_SIZES = [10, 25, 50, 100]
const REFRESH_MS = 5000

function pad(value) {
  return String(value).padStart(2, '0')
}

function toInput(iso) {
  const date = new Date(iso)
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`
}

function fromInput(value) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    return null
  }
  return `${value}:00Z`
}

function defaultRange() {
  const start = new Date(Date.now() + 60 * 60 * 1000)
  const end = new Date(Date.now() + 2 * 60 * 60 * 1000)
  return { start: toInput(start.toISOString()), end: toInput(end.toISOString()) }
}

function pageCountOf(total, pageSize) {
  return Math.max(1, Math.ceil(total / pageSize))
}

export default function Maintenances({ token, onError }) {
  const [data, setData] = useState(null)
  const [urlPage, setUrlPage] = useState(1)
  const [urlPageSize, setUrlPageSize] = useState(10)
  const [groupPage, setGroupPage] = useState(1)
  const [groupPageSize, setGroupPageSize] = useState(10)
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')

  const tokenRef = useRef(token)
  const onErrorRef = useRef(onError)
  const pagesRef = useRef({ urlPage, urlPageSize, groupPage, groupPageSize })
  const skipCommit = useRef(false)
  const creating = useRef(false)
  const draftRef = useRef(draft)
  tokenRef.current = token
  onErrorRef.current = onError
  pagesRef.current = { urlPage, urlPageSize, groupPage, groupPageSize }
  draftRef.current = draft

  function query() {
    const current = pagesRef.current
    return `url_page=${current.urlPage}&url_page_size=${current.urlPageSize}&group_page=${current.groupPage}&group_page_size=${current.groupPageSize}`
  }

  function pagesBody() {
    const current = pagesRef.current
    return {
      url_page: current.urlPage,
      url_page_size: current.urlPageSize,
      group_page: current.groupPage,
      group_page_size: current.groupPageSize,
    }
  }

  function apply(payload) {
    setData(payload)
    setUrlPage(payload.url_page)
    setUrlPageSize(payload.url_page_size)
    setGroupPage(payload.group_page)
    setGroupPageSize(payload.group_page_size)
  }

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const payload = await api(`/api/maintenances?${query()}`, { token: tokenRef.current })
        if (active) {
          apply(payload)
        }
      } catch (error) {
        if (active) {
          onErrorRef.current(error)
        }
      }
    }

    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [token, urlPage, urlPageSize, groupPage, groupPageSize])

  function report(error) {
    onErrorRef.current(error)
  }

  async function createRow(kind, rawId, startsAt, endsAt) {
    const targetId = Number(rawId)
    if (!rawId || !Number.isInteger(targetId)) {
      return false
    }
    if (!startsAt || !endsAt || endsAt <= startsAt) {
      report(new Error('Maintenance end must be after the start.'))
      return false
    }
    if (creating.current) {
      return false
    }
    creating.current = true
    try {
      const payload = await api('/api/maintenances', {
        method: 'POST',
        token: tokenRef.current,
        body: {
          target_kind: kind,
          target_id: targetId,
          starts_at: startsAt,
          ends_at: endsAt,
          ...pagesBody(),
        },
      })
      apply(payload)
      return true
    } catch (error) {
      report(error)
      return false
    } finally {
      creating.current = false
    }
  }

  async function saveRow(row, startsAt, endsAt, targetId) {
    if (!startsAt || !endsAt || endsAt <= startsAt) {
      report(new Error('Maintenance end must be after the start.'))
      return
    }
    if (
      startsAt === fromInput(toInput(row.starts_at))
      && endsAt === fromInput(toInput(row.ends_at))
      && targetId === row.target_id
    ) {
      return
    }
    try {
      const payload = await api('/api/maintenances', {
        method: 'PATCH',
        token: tokenRef.current,
        body: {
          id: row.id,
          target_kind: row.target_kind,
          target_id: targetId,
          starts_at: startsAt,
          ends_at: endsAt,
          ...pagesBody(),
        },
      })
      apply(payload)
    } catch (error) {
      report(error)
    }
  }

  async function remove(row) {
    try {
      const payload = await api('/api/maintenances/delete', {
        method: 'POST',
        token: tokenRef.current,
        body: { id: row.id, ...pagesBody() },
      })
      apply(payload)
    } catch (error) {
      report(error)
    }
  }

  function timeValue(row, field) {
    if (editing?.id === row.id && editing.field === field) {
      return draft
    }
    return toInput(row[field])
  }

  function commitTime(row, field) {
    if (skipCommit.current) {
      skipCommit.current = false
      setEditing(null)
      return
    }
    const next = draftRef.current
    setEditing(null)
    const startsAt = field === 'starts_at' ? fromInput(next) : fromInput(toInput(row.starts_at))
    const endsAt = field === 'ends_at' ? fromInput(next) : fromInput(toInput(row.ends_at))
    saveRow(row, startsAt, endsAt, row.target_id)
  }

  const urls = data?.urls ?? []
  const groups = data?.groups ?? []

  return (
    <>
      <MaintenanceTable
        title="URL maintenances"
        kind="url"
        rows={data?.url_maintenances ?? []}
        total={data?.url_total ?? 0}
        page={urlPage}
        pageSize={urlPageSize}
        options={urls.map((item) => ({ id: item.id, label: item.url }))}
        onPage={setUrlPage}
        onPageSize={(size) => {
          setUrlPageSize(size)
          setUrlPage(1)
        }}
        onCreate={(rawId, startsAt, endsAt) => createRow('url', rawId, startsAt, endsAt)}
        onTarget={(row, targetId) => {
          saveRow(row, fromInput(toInput(row.starts_at)), fromInput(toInput(row.ends_at)), targetId)
        }}
        onRemove={remove}
        timeValue={timeValue}
        onFocusTime={(row, field) => {
          setEditing({ id: row.id, field })
          setDraft(toInput(row[field]))
        }}
        onDraft={setDraft}
        onCommitTime={commitTime}
        onTimeKeyDown={(event, row, field) => {
          if (event.key === 'Enter') {
            event.currentTarget.blur()
          }
          if (event.key === 'Escape') {
            skipCommit.current = true
            setDraft(toInput(row[field]))
            event.currentTarget.blur()
          }
        }}
      />
      <MaintenanceTable
        title="Group maintenances"
        kind="group"
        rows={data?.group_maintenances ?? []}
        total={data?.group_total ?? 0}
        page={groupPage}
        pageSize={groupPageSize}
        options={groups.map((item) => ({ id: item.id, label: item.name }))}
        onPage={setGroupPage}
        onPageSize={(size) => {
          setGroupPageSize(size)
          setGroupPage(1)
        }}
        onCreate={(rawId, startsAt, endsAt) => createRow('group', rawId, startsAt, endsAt)}
        onTarget={(row, targetId) => {
          saveRow(row, fromInput(toInput(row.starts_at)), fromInput(toInput(row.ends_at)), targetId)
        }}
        onRemove={remove}
        timeValue={timeValue}
        onFocusTime={(row, field) => {
          setEditing({ id: row.id, field })
          setDraft(toInput(row[field]))
        }}
        onDraft={setDraft}
        onCommitTime={commitTime}
        onTimeKeyDown={(event, row, field) => {
          if (event.key === 'Enter') {
            event.currentTarget.blur()
          }
          if (event.key === 'Escape') {
            skipCommit.current = true
            setDraft(toInput(row[field]))
            event.currentTarget.blur()
          }
        }}
      />
    </>
  )
}

function MaintenanceTable({
  title,
  kind,
  rows,
  total,
  page,
  pageSize,
  options,
  onPage,
  onPageSize,
  onCreate,
  onTarget,
  onRemove,
  timeValue,
  onFocusTime,
  onDraft,
  onCommitTime,
  onTimeKeyDown,
}) {
  const initialRange = defaultRange()
  const [blankStart, setBlankStart] = useState(initialRange.start)
  const [blankEnd, setBlankEnd] = useState(initialRange.end)
  const pageCount = pageCountOf(total, pageSize)
  const targetLabel = kind === 'url' ? 'URL' : 'Group'

  async function create(rawId) {
    const saved = await onCreate(rawId, fromInput(blankStart), fromInput(blankEnd))
    if (saved) {
      const next = defaultRange()
      setBlankStart(next.start)
      setBlankEnd(next.end)
    }
  }

  return (
    <section>
      <h2>{title}</h2>
      <table>
        <thead>
          <tr>
            <th>{targetLabel}</th>
            <th>Start (UTC)</th>
            <th>End (UTC)</th>
            <th>Status</th>
            <th>Delete</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <select
                  aria-label={`${targetLabel} for maintenance ${row.id}`}
                  value={String(row.target_id)}
                  onChange={(event) => onTarget(row, Number(event.target.value))}
                >
                  {options.map((option) => (
                    <option key={option.id} value={String(option.id)}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="datetime-local"
                  aria-label={`Start for maintenance ${row.id}`}
                  value={timeValue(row, 'starts_at')}
                  onFocus={() => onFocusTime(row, 'starts_at')}
                  onChange={(event) => onDraft(event.target.value)}
                  onBlur={() => onCommitTime(row, 'starts_at')}
                  onKeyDown={(event) => onTimeKeyDown(event, row, 'starts_at')}
                />
              </td>
              <td>
                <input
                  type="datetime-local"
                  aria-label={`End for maintenance ${row.id}`}
                  value={timeValue(row, 'ends_at')}
                  onFocus={() => onFocusTime(row, 'ends_at')}
                  onChange={(event) => onDraft(event.target.value)}
                  onBlur={() => onCommitTime(row, 'ends_at')}
                  onKeyDown={(event) => onTimeKeyDown(event, row, 'ends_at')}
                />
              </td>
              <td>{row.status}</td>
              <td>
                <button type="button" title="Delete maintenance" onMouseDown={(event) => event.preventDefault()} onClick={() => onRemove(row)}>
                  [X]
                </button>
              </td>
            </tr>
          ))}
          <tr>
            <td>
              <select
                aria-label={`New ${targetLabel} maintenance`}
                value=""
                onChange={(event) => create(event.target.value)}
              >
                <option value="">NONE</option>
                {options.map((option) => (
                  <option key={option.id} value={String(option.id)}>
                    {option.label}
                  </option>
                ))}
              </select>
            </td>
            <td>
              <input
                type="datetime-local"
                aria-label={`New ${targetLabel} maintenance start`}
                value={blankStart}
                onChange={(event) => onBlankStart(event.target.value)}
              />
            </td>
            <td>
              <input
                type="datetime-local"
                aria-label={`New ${targetLabel} maintenance end`}
                value={blankEnd}
                onChange={(event) => onBlankEnd(event.target.value)}
              />
            </td>
            <td />
            <td />
          </tr>
        </tbody>
      </table>
      <div className="pager">
        <label>
          Page size{' '}
          <select
            aria-label={`${title} page size`}
            value={pageSize}
            onChange={(event) => onPageSize(Number(event.target.value))}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>{' '}
        <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1}>
          Previous
        </button>{' '}
        <span>
          Page {Math.min(page, pageCount)} of {pageCount}
        </span>{' '}
        <button type="button" onClick={() => onPage(page + 1)} disabled={page >= pageCount}>
          Next
        </button>
      </div>
    </section>
  )
}
