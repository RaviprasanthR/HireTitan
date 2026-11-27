/** The URL when it is http(s), else undefined, so a stored `javascript:` link renders inert. */
export function safeHttpUrl(url: string | null | undefined): string | undefined {
  const u = url?.trim()
  return u && /^https?:\/\//i.test(u) ? u : undefined
}
