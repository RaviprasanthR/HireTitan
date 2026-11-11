import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/api/client'
import type { components } from '@/api/schema'

export type Company = components['schemas']['CompanyOut']
export type CompanyPage = components['schemas']['CompanyPage']
export type Discovery = components['schemas']['DiscoveryOut']
export type ImportPreview = components['schemas']['ImportPreview']
export type ImportResult = components['schemas']['ImportResult']

export type CompanyFilter = 'all' | 'check_manually'
export type CompanyFields = { name: string; careers_url: string; city?: string; website?: string }
export type CompanyEdit = Partial<{
  name: string
  city: string
  website: string
  careers_url: string
  hidden: boolean
}>

export const BOARD_STATUS: Record<Company['board_status'], string> = {
  board: 'Job board',
  careers_page: 'Careers page',
  check_manually: 'Check manually',
  unsupported: 'Board not supported',
  unresolved: 'Not set up',
}

export const EXPORT_URL = '/api/v1/companies/export'

function useRefreshCompanies() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: ['companies'] })
}

export function useCompanies(filter: CompanyFilter) {
  return useQuery({
    queryKey: ['companies', filter],
    queryFn: () =>
      apiFetch<CompanyPage>(filter === 'all' ? '/companies' : `/companies?filter=${filter}`),
  })
}

export function useEditCompany() {
  const refresh = useRefreshCompanies()
  return useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: CompanyEdit }) =>
      apiFetch<Company>(`/companies/${id}`, { method: 'PATCH', json: changes }),
    onSuccess: refresh,
  })
}

export function useDeleteCompany() {
  const refresh = useRefreshCompanies()
  return useMutation({
    mutationFn: (id: string) => apiFetch(`/companies/${id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
}

export function useAddCompany() {
  const refresh = useRefreshCompanies()
  return useMutation({
    mutationFn: (fields: CompanyFields) =>
      apiFetch<Company>('/companies', { method: 'POST', json: fields }),
    onSuccess: refresh,
  })
}

export function useDiscovery(id: string) {
  return useQuery({
    queryKey: ['companies', 'discovery', id],
    queryFn: () => apiFetch<Discovery>(`/companies/${id}/discovery`),
    staleTime: Infinity,
  })
}

export function useDecideBoard(id: string) {
  const refresh = useRefreshCompanies()
  return useMutation({
    mutationFn: (decision: 'confirm' | 'reject') =>
      apiFetch<Company>(`/companies/${id}/discovery/${decision}`, { method: 'POST' }),
    onSuccess: refresh,
  })
}

export function usePreviewImport() {
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return apiFetch<ImportPreview>('/companies/import', { method: 'POST', body })
    },
  })
}

export function useConfirmImport() {
  const refresh = useRefreshCompanies()
  return useMutation({
    mutationFn: (token: string) =>
      apiFetch<ImportResult>(`/companies/import/${token}/confirm`, { method: 'POST' }),
    onSuccess: refresh,
  })
}

export type SheetPreview = components['schemas']['SheetPreview']
export type SheetResult = components['schemas']['SheetResult']

export function useSheetPreview() {
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return apiFetch<SheetPreview>('/companies/sheet-import', { method: 'POST', body })
    },
  })
}

export function useSheetConfirm() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (token: string) =>
      apiFetch<SheetResult>(`/companies/sheet-import/${token}/confirm`, { method: 'POST' }),
    // contacts and notes show on the Companies page, so refresh it with the list
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['companies'] }),
        client.invalidateQueries({ queryKey: ['contacts'] }), // open panels and note editors
      ]),
  })
}

export type Contact = components['schemas']['ContactOut']
export type ContactsPanelData = components['schemas']['ContactsOut']
export type Note = components['schemas']['NoteOut']
export type ContactInput = {
  name: string
  role: string
  linkedin_url: string
  email: string
  phone: string
  confidence: string
  note: string
}

function useRefreshContacts(companyId: string) {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ['contacts', companyId] }),
      client.invalidateQueries({ queryKey: ['companies'] }), // the list shows the counts
    ])
}

export function useContacts(companyId: string) {
  return useQuery({
    queryKey: ['contacts', companyId],
    queryFn: () => apiFetch<ContactsPanelData>(`/companies/${companyId}/contacts`),
  })
}

export function useAddContact(companyId: string) {
  const refresh = useRefreshContacts(companyId)
  return useMutation({
    mutationFn: (values: ContactInput) =>
      apiFetch<Contact>(`/companies/${companyId}/contacts`, { method: 'POST', json: values }),
    onSuccess: refresh,
  })
}

export function useEditContact(companyId: string) {
  const refresh = useRefreshContacts(companyId)
  return useMutation({
    mutationFn: ({ id, values }: { id: string; values: ContactInput }) =>
      apiFetch<Contact>(`/companies/${companyId}/contacts/${id}`, {
        method: 'PATCH',
        json: values,
      }),
    onSuccess: refresh,
  })
}

export function useDeleteContact(companyId: string) {
  const refresh = useRefreshContacts(companyId)
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/companies/${companyId}/contacts/${id}`, { method: 'DELETE' }),
    onSuccess: refresh,
  })
}

export function useSaveNote(companyId: string) {
  const refresh = useRefreshContacts(companyId)
  return useMutation({
    mutationFn: (body: string) =>
      apiFetch<Note>(`/companies/${companyId}/note`, { method: 'PUT', json: { body } }),
    onSuccess: refresh,
  })
}
