import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

const REFRESH_MS = 5000

export default function Mailing({ token, onError }) {
  const [mails, setMails] = useState([])
  const tokenRef = useRef(token)
  const onErrorRef = useRef(onError)
  tokenRef.current = token
  onErrorRef.current = onError

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const data = await api('/api/mails', { token: tokenRef.current })
        if (active) {
          setMails(data.mails)
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

  return (
    <>
      <h2>Sent emails</h2>
      {mails.length === 0 ? <p>No emails yet.</p> : null}
      <table>
        <thead>
          <tr>
            <th>To</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {mails.map((mail) => (
            <tr key={mail.id}>
              <td>{mail.addresses.join(', ')}</td>
              <td className="mail-message">{mail.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
