export async function api<T>(route:string, body?:object):Promise<T> {
  const response = await fetch(route, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : undefined)
  const result = await response.json()
  if (!response.ok) throw new Error(result.error || '请求失败')
  return result as T
}

