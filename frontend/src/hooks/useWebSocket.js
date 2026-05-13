import { useEffect, useRef, useState } from 'react'

export function useWebSocket(url, { enabled = true, onMessage } = {}) {
  const socketRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [messages, setMessages] = useState([])
  const [lastMessage, setLastMessage] = useState(null)

  useEffect(() => {
    if (!enabled || !url) return undefined

    const socket = new WebSocket(url)
    socketRef.current = socket

    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)
    socket.onmessage = (event) => {
      let payload = event.data
      try {
        payload = JSON.parse(event.data)
      } catch {
        // keep raw payload
      }
      setLastMessage(payload)
      setMessages((prev) => [payload, ...prev].slice(0, 50))
      if (onMessage) onMessage(payload)
    }

    return () => {
      socket.close()
      socketRef.current = null
    }
  }, [url, enabled, onMessage])

  return { connected, messages, lastMessage, socket: socketRef.current }
}

