import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { api } = vi.hoisted(() => ({
  api: {
    getMessages: vi.fn(),
    getMessageThread: vi.fn(),
  },
}))

vi.mock('../services/api', () => ({ api }))

import Messages from './Messages'

function renderMessages(initialEntry = '/messages') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/messages" element={<Messages />} />
      </Routes>
    </MemoryRouter>
  )
}

function makeMessage(overrides = {}) {
  return {
    id: 1,
    message_type: 'direct_message',
    content: 'Direct coordination message',
    created_at: '2026-04-21T02:20:00.000Z',
    author: { agent_number: 7, display_name: 'Agent 7' },
    recipient: { agent_number: 11, display_name: 'Agent 11' },
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getMessages.mockImplementation(async (_limit, messageType) => {
    if (messageType === 'forum_post') return []
    if (messageType === 'forum_reply') return []
    if (messageType === 'direct_message') return [makeMessage()]
    return []
  })
  api.getMessageThread.mockResolvedValue(null)
})

afterEach(() => {
  cleanup()
})

describe('Messages', () => {
  it('defaults to all messages so direct-only activity is still visible', async () => {
    renderMessages('/messages')

    expect(await screen.findByRole('heading', { name: /All Messages/i })).toBeInTheDocument()
    expect(screen.getByText(/Direct coordination message/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /All Messages/i })).toHaveClass('active')
  })

  it('still respects an explicit forum tab query parameter', async () => {
    renderMessages('/messages?tab=forum')

    expect(await screen.findByRole('heading', { name: /Forum Posts/i })).toBeInTheDocument()
    expect(screen.getByText(/No messages in this view yet/i)).toBeInTheDocument()
  })

  it('includes follow-up direct messages in the replies view', async () => {
    api.getMessages.mockImplementation(async (_limit, messageType) => {
      if (messageType === 'forum_post') return []
      if (messageType === 'forum_reply') return []
      if (messageType === 'direct_message') {
        return [
          makeMessage({
            id: 1,
            content: 'Initial outreach',
            created_at: '2026-04-21T02:20:00.000Z',
          }),
          makeMessage({
            id: 2,
            content: 'Follow-up response',
            created_at: '2026-04-21T02:21:00.000Z',
            author: { agent_number: 11, display_name: 'Agent 11' },
            recipient: { agent_number: 7, display_name: 'Agent 7' },
          }),
          makeMessage({
            id: 3,
            content: 'Second follow-up',
            created_at: '2026-04-21T02:22:00.000Z',
          }),
        ]
      }
      return []
    })

    renderMessages('/messages?tab=replies')

    expect(await screen.findByRole('heading', { name: /^Replies$/i })).toBeInTheDocument()
    expect(screen.queryByText(/Initial outreach/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Follow-up response/i)).toBeInTheDocument()
    expect(screen.getByText(/Second follow-up/i)).toBeInTheDocument()
  })

  it('does not duplicate direct follow-ups in all messages', async () => {
    api.getMessages.mockImplementation(async (_limit, messageType) => {
      if (messageType === 'forum_post') {
        return [
          makeMessage({
            id: 10,
            message_type: 'forum_post',
            content: 'Public forum post',
            recipient: null,
            created_at: '2026-04-21T02:19:00.000Z',
          }),
        ]
      }
      if (messageType === 'forum_reply') return []
      if (messageType === 'direct_message') {
        return [
          makeMessage({
            id: 1,
            content: 'Initial outreach',
            created_at: '2026-04-21T02:20:00.000Z',
          }),
          makeMessage({
            id: 2,
            content: 'Follow-up response',
            created_at: '2026-04-21T02:21:00.000Z',
            author: { agent_number: 11, display_name: 'Agent 11' },
            recipient: { agent_number: 7, display_name: 'Agent 7' },
          }),
        ]
      }
      return []
    })

    renderMessages('/messages')

    expect(await screen.findByRole('heading', { name: /All Messages/i })).toBeInTheDocument()
    expect(screen.getByText(/Public forum post/i)).toBeInTheDocument()
    expect(screen.getByText(/Initial outreach/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Follow-up response/i)).toHaveLength(1)
  })
})
