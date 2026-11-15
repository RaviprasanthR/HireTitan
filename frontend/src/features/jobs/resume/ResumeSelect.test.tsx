import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { offeredResumes } from './resumeApi'
import { ResumeSelect } from './ResumeSelect'

function file(id: string, name: string, createdAt: string, status = 'parsed') {
  return {
    id,
    kind: 'upload_pdf',
    original_name: name,
    size_bytes: 1000,
    page_count: 1,
    parse_status: status,
    parse_result: null,
    created_at: createdAt,
    has_open_review: false,
    open_review_id: null,
  }
}

const FILES = [
  file('f1', 'Backend_2024.pdf', '2025-03-14T09:00:00Z'),
  file('f2', 'Backend_2025.pdf', '2026-10-02T09:00:00Z'),
  file('f3', 'Letter.pdf', '2026-11-01T09:00:00Z', 'not_resume'),
  file('f4', 'Fresh.pdf', '2026-11-05T09:00:00Z', 'pending'),
]

describe('offeredResumes', () => {
  it('US1 AS1 lists the files newest first and leaves out one rejected as not a resume', () => {
    expect(offeredResumes(FILES).map((f) => f.id)).toEqual(['f4', 'f2', 'f1'])
  })

  it('FR012 offers a file that is still being read', () => {
    expect(offeredResumes(FILES).map((f) => f.parse_status)).toContain('pending')
  })
})

describe('ResumeSelect', () => {
  it('US1 AS1 lists the files by name and added day, then None', () => {
    render(<ResumeSelect files={offeredResumes(FILES)} value="" onChange={() => {}} />)

    const select = screen.getByRole('combobox', { name: 'Resume used' })
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'None',
      'Fresh.pdf · added 5 Nov 2026',
      'Backend_2025.pdf · added 2 Oct 2026',
      'Backend_2024.pdf · added 14 Mar 2025',
    ])
  })

  it('US1 AS6 shows nothing when there are no stored files', () => {
    const { container } = render(<ResumeSelect files={[]} value="" onChange={() => {}} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('shows the chosen file and reports a change, with None as an empty value', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ResumeSelect files={offeredResumes(FILES)} value="f2" onChange={onChange} />)
    const select = screen.getByRole('combobox', { name: 'Resume used' })
    expect(select).toHaveValue('f2')

    await user.selectOptions(select, 'f1')
    await user.selectOptions(select, 'None')

    expect(onChange.mock.calls).toEqual([['f1'], ['']])
  })
})
