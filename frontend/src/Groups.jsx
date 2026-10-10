import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

const REFRESH_MS = 5000
const NAME_LIMIT = 50

export default function Groups({ token, onError }) {
  const [groups, setGroups] = useState([])
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')
  const [blankName, setBlankName] = useState('')
  const [mailGroupId, setMailGroupId] = useState(null)
  const [blankEmail, setBlankEmail] = useState('')

  const skipCommit = useRef(false)
  const creating = useRef(false)
  const groupsRef = useRef(groups)
  const draftRef = useRef(draft)
  const blankNameRef = useRef(blankName)
  const blankEmailRef = useRef(blankEmail)
  const tokenRef = useRef(token)
  const onErrorRef = useRef(onError)
  groupsRef.current = groups
  draftRef.current = draft
  blankNameRef.current = blankName
  blankEmailRef.current = blankEmail
  tokenRef.current = token
  onErrorRef.current = onError

  const mailGroup = groups.find((group) => group.id === mailGroupId) ?? null

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const data = await api('/api/groups', { token: tokenRef.current })
        if (active) {
          setGroups(data.groups)
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
  }, [token])

  function report(error) {
    onErrorRef.current(error)
  }

  async function saveName(groupId, text) {
    const group = groupsRef.current.find((item) => item.id === groupId)
    if (!group) {
      return true
    }
    const name = text.trim()
    if (!name) {
      report(new Error('Name is required.'))
      return false
    }
    if (name.length > NAME_LIMIT) {
      report(new Error('Name must be at most 50 characters.'))
      return false
    }
    if (name === group.name) {
      return true
    }
    try {
      const data = await api('/api/groups', {
        method: 'PATCH',
        token: tokenRef.current,
        body: { id: groupId, name },
      })
      setGroups(data.groups)
      return true
    } catch (error) {
      report(error)
      return false
    }
  }

  async function createFrom(text) {
    const name = text.trim()
    if (!name) {
      return true
    }
    if (name.length > NAME_LIMIT) {
      report(new Error('Name must be at most 50 characters.'))
      return false
    }
    if (creating.current) {
      return false
    }
    creating.current = true
    try {
      const data = await api('/api/groups', {
        method: 'POST',
        token: tokenRef.current,
        body: { name },
      })
      setGroups(data.groups)
      setBlankName('')
      return true
    } catch (error) {
      report(error)
      return false
    } finally {
      creating.current = false
    }
  }

  async function saveEmailAddress(emailId, text) {
    const address = text.trim()
    if (!address) {
      report(new Error('Email is required.'))
      return false
    }
    const current = mailGroup?.emails.find((item) => item.id === emailId)
    if (current && current.address === address) {
      return true
    }
    try {
      const data = await api('/api/groups/emails', {
        method: 'PATCH',
        token: tokenRef.current,
        body: { id: emailId, address },
      })
      setGroups(data.groups)
      return true
    } catch (error) {
      report(error)
      return false
    }
  }

  async function createEmail(text) {
    const address = text.trim()
    if (!address || mailGroupId == null) {
      return true
    }
    if (creating.current) {
      return false
    }
    creating.current = true
    try {
      const data = await api('/api/groups/emails', {
        method: 'POST',
        token: tokenRef.current,
        body: { group_id: mailGroupId, address },
      })
      setGroups(data.groups)
      setBlankEmail('')
      return true
    } catch (error) {
      report(error)
      return false
    } finally {
      creating.current = false
    }
  }

  function blurName(group) {
    if (skipCommit.current) {
      skipCommit.current = false
      setEditing(null)
      return
    }
    const text = draftRef.current
    setEditing(null)
    saveName(group.id, text)
  }

  function blurBlank() {
    if (skipCommit.current) {
      skipCommit.current = false
      return
    }
    createFrom(blankNameRef.current)
  }

  function blurEmail(email) {
    if (skipCommit.current) {
      skipCommit.current = false
      setEditing(null)
      return
    }
    const text = draftRef.current
    setEditing(null)
    saveEmailAddress(email.id, text)
  }

  function blurBlankEmail() {
    if (skipCommit.current) {
      skipCommit.current = false
      return
    }
    createEmail(blankEmailRef.current)
  }

  function onKeyDown(event, restore) {
    if (event.key !== 'Escape') {
      return
    }
    skipCommit.current = true
    restore()
    setEditing(null)
    event.currentTarget.blur()
  }

  async function commitFocused() {
    const active = document.activeElement
    if (!(active instanceof HTMLInputElement) || !active.dataset.commit) {
      return true
    }
    const commit = active.dataset.commit
    const groupId = Number(active.dataset.groupId || 0)
    const emailId = Number(active.dataset.emailId || 0)
    const text = active.value
    skipCommit.current = true
    active.blur()
    if (commit === 'name') {
      return saveName(groupId, text)
    }
    if (commit === 'blank') {
      return createFrom(text)
    }
    if (commit === 'email') {
      return saveEmailAddress(emailId, text)
    }
    if (commit === 'email-blank') {
      return createEmail(text)
    }
    return true
  }

  async function toggle(group) {
    const saved = await commitFocused()
    if (!saved) {
      return
    }
    try {
      const data = await api('/api/groups', {
        method: 'PATCH',
        token: tokenRef.current,
        body: { id: group.id, paused: !group.paused },
      })
      setGroups(data.groups)
    } catch (error) {
      report(error)
    }
  }

  async function remove(group) {
    const saved = await commitFocused()
    if (!saved) {
      return
    }
    try {
      const data = await api('/api/groups/delete', {
        method: 'POST',
        token: tokenRef.current,
        body: { id: group.id },
      })
      setGroups(data.groups)
      if (mailGroupId === group.id) {
        setMailGroupId(null)
      }
    } catch (error) {
      report(error)
    }
  }

  async function removeEmail(email) {
    const saved = await commitFocused()
    if (!saved) {
      return
    }
    try {
      const data = await api('/api/groups/emails/delete', {
        method: 'POST',
        token: tokenRef.current,
        body: { id: email.id },
      })
      setGroups(data.groups)
    } catch (error) {
      report(error)
    }
  }

  async function openMail(group) {
    const saved = await commitFocused()
    if (!saved) {
      return
    }
    setMailGroupId(group.id)
    setBlankEmail('')
    setEditing(null)
  }

  return (
    <>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Name</th>
            <th>URLs</th>
            <th>Play / pause</th>
            <th>Health</th>
            <th>Status</th>
            <th>Delete</th>
            <th>Email</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const naming = editing?.id === group.id && editing.field === 'name'
            return (
              <tr key={group.id}>
                <td>{group.id}</td>
                <td>
                  <input
                    type="text"
                    aria-label={`Name for group ${group.id}`}
                    maxLength={NAME_LIMIT}
                    data-commit="name"
                    data-group-id={group.id}
                    value={naming ? draft : group.name}
                    onFocus={() => {
                      setEditing({ id: group.id, field: 'name' })
                      setDraft(group.name)
                    }}
                    onChange={(event) => setDraft(event.target.value)}
                    onBlur={() => blurName(group)}
                    onKeyDown={(event) => onKeyDown(event, () => setDraft(group.name))}
                  />
                </td>
                <td>{group.url_count}</td>
                <td>
                  <button
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => toggle(group)}
                  >
                    {group.paused ? 'Play' : 'Pause'}
                  </button>
                </td>
                <td>{group.health}</td>
                <td>{group.response_status}</td>
                <td>
                  <button
                    type="button"
                    title="Delete group"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => remove(group)}
                  >
                    [X]
                  </button>
                </td>
                <td>
                  <button
                    type="button"
                    title="Email addresses"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => openMail(group)}
                  >
                    [M]
                  </button>
                </td>
              </tr>
            )
          })}
          <tr>
            <td />
            <td>
              <input
                type="text"
                aria-label="New group name"
                maxLength={NAME_LIMIT}
                data-commit="blank"
                value={blankName}
                onChange={(event) => setBlankName(event.target.value)}
                onBlur={blurBlank}
                onKeyDown={(event) => onKeyDown(event, () => setBlankName(''))}
              />
            </td>
            <td />
            <td />
            <td />
            <td />
            <td />
            <td />
          </tr>
        </tbody>
      </table>
      {mailGroup ? (
        <div className="popup-backdrop">
          <div className="popup" role="dialog" aria-label={`Email addresses for ${mailGroup.name}`}>
            <p>Email addresses for {mailGroup.name}</p>
            <table>
              <tbody>
                {mailGroup.emails.map((email) => {
                  const naming = editing?.id === email.id && editing.field === 'email'
                  return (
                    <tr key={email.id}>
                      <td>
                        <input
                          type="text"
                          aria-label={`Email ${email.id}`}
                          data-commit="email"
                          data-email-id={email.id}
                          value={naming ? draft : email.address}
                          onFocus={() => {
                            setEditing({ id: email.id, field: 'email' })
                            setDraft(email.address)
                          }}
                          onChange={(event) => setDraft(event.target.value)}
                          onBlur={() => blurEmail(email)}
                          onKeyDown={(event) => onKeyDown(event, () => setDraft(email.address))}
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          title="Delete email"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => removeEmail(email)}
                        >
                          [X]
                        </button>
                      </td>
                    </tr>
                  )
                })}
                <tr>
                  <td>
                    <input
                      type="text"
                      aria-label="New email"
                      data-commit="email-blank"
                      value={blankEmail}
                      onChange={(event) => setBlankEmail(event.target.value)}
                      onBlur={blurBlankEmail}
                      onKeyDown={(event) => onKeyDown(event, () => setBlankEmail(''))}
                    />
                  </td>
                  <td />
                </tr>
              </tbody>
            </table>
            <div className="popup-actions">
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={async () => {
                  const saved = await commitFocused()
                  if (saved) {
                    setMailGroupId(null)
                  }
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
