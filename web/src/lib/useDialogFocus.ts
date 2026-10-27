import { useEffect, useRef } from 'react'

/** Keep keyboard interaction inside an open modal and restore its trigger. */
export function useDialogFocus<T extends HTMLElement>(open:boolean) {
  const ref=useRef<T>(null)
  useEffect(()=>{
    const dialog=ref.current
    if(!open||!dialog)return
    const previous=document.activeElement
    const controls=()=>Array.from(dialog.querySelectorAll<HTMLElement>('button,input,textarea,select,a[href],[tabindex]'))
      .filter(element=>element.tabIndex>=0&&!element.matches(':disabled')&&element.getClientRects().length>0)
    if(!dialog.contains(document.activeElement))
      (dialog.querySelector<HTMLElement>('[data-dialog-initial-focus]')??controls()[0]??dialog).focus()
    const trap=(event:KeyboardEvent)=>{
      if(event.key!=='Tab')return
      const items=controls(),first=items[0],last=items.at(-1)
      if(!first){event.preventDefault();dialog.focus();return}
      if(!dialog.contains(document.activeElement)||document.activeElement===dialog){event.preventDefault();(event.shiftKey?last:first)?.focus()}
      else if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
    }
    window.addEventListener('keydown',trap)
    return()=>{window.removeEventListener('keydown',trap);if(previous instanceof HTMLElement&&previous.isConnected)previous.focus()}
  },[open])
  return ref
}
