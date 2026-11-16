import { useEffect } from 'react'

let working = 0

/** While something is in progress, the page says so (`html[data-working]`) and the logo keeps turning. */
export function useWorking(active: boolean) {
  useEffect(() => {
    if (!active) return
    working += 1
    document.documentElement.dataset.working = 'true'
    return () => {
      working -= 1
      if (working <= 0) delete document.documentElement.dataset.working
    }
  }, [active])
}
