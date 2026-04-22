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
})
