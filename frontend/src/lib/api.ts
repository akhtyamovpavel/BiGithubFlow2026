import type {
  Group,
  GroupFilters,
  GroupInput,
  Lesson,
  Readiness,
  Teacher,
  TeacherFilters,
  TeacherInput,
} from "@/lib/models"

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "")
const healthDefault = new URL(API_BASE_URL, window.location.origin).origin + "/health/ready"
const HEALTH_URL = import.meta.env.VITE_HEALTH_URL || healthDefault

interface ValidationIssue {
  loc: (string | number)[]
  msg: string
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: Record<string, string> = {},
  ) {
    super(message)
    this.name = "ApiError"
  }
}

function isValidationIssue(value: unknown): value is ValidationIssue {
  if (!value || typeof value !== "object") {
    return false
  }
  return (
    "loc" in value && Array.isArray(value.loc) && "msg" in value && typeof value.msg === "string"
  )
}

async function responseError(response: Response): Promise<ApiError> {
  let detail: unknown
  try {
    const body: unknown = await response.json()
    if (body && typeof body === "object" && "detail" in body) {
      detail = body.detail
    }
  } catch {
    // Proxies can return HTML instead of FastAPI's JSON error body.
  }
  const messages: Record<number, string> = {
    404: "Запись не найдена. Возможно, её уже удалили. Обнови список.",
    409: "Не удалось сохранить: запись с такими данными уже существует или связана с расписанием.",
    422: "Проверь значения полей формы.",
    503: "Сервис временно недоступен. Попробуй ещё раз позже.",
  }
  const fields: Record<string, string> = {}
  if (Array.isArray(detail)) {
    for (const issue of detail.filter(isValidationIssue)) {
      const field = issue.loc.at(-1)
      if (typeof field === "string") {
        fields[field] = issue.msg
      }
    }
  }
  const message =
    messages[response.status] || `Ошибка сервера (${response.status}). Попробуй ещё раз.`
  return new ApiError(response.status, message, fields)
}

export async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 15000)
  let signal = controller.signal
  if (options.signal) {
    signal = AbortSignal.any([options.signal, controller.signal])
  }
  try {
    const response = await fetch(url, {
      ...options,
      signal,
      headers: { Accept: "application/json", ...options.headers },
    })
    if (!response.ok) {
      throw await responseError(response)
    }
    if (response.status === 204) {
      return undefined as T
    }
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    if (signal.aborted && options.signal?.aborted) {
      throw error
    }
    throw new ApiError(0, "Нет связи с сервером. Проверь подключение и повтори запрос.")
  } finally {
    window.clearTimeout(timeout)
  }
}

export function queryString(filters: object): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") {
      params.set(key, String(value))
    }
  }
  return params.toString()
}

function createResource<T, Input, Filters extends object>(resource: string) {
  const url = `${API_BASE_URL}/${resource}`
  return {
    list: async (filters: Filters, signal?: AbortSignal) => {
      const records = await request<T[]>(`${url}/?${queryString(filters)}`, { signal })
      if (!Array.isArray(records)) {
        throw new ApiError(0, "Сервис вернул данные в неизвестном формате.")
      }
      return records
    },
    save: (input: Input, id?: number) => {
      let target = `${url}/`
      let method = "POST"
      if (id !== undefined) {
        target = `${url}/${id}`
        method = "PUT"
      }
      return request<T>(target, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      })
    },
    remove: (id: number) => request<void>(`${url}/${id}`, { method: "DELETE" }),
  }
}

export const groupsApi = createResource<Group, GroupInput, GroupFilters>("groups")
export const teachersApi = createResource<Teacher, TeacherInput, TeacherFilters>("teachers")
export const getReadiness = (signal?: AbortSignal) => request<Readiness>(HEALTH_URL, { signal })
export const getLessons = async (signal?: AbortSignal) => {
  const path = import.meta.env.VITE_SCHEDULE_PATH || "/lessons/"
  const lessons = await request<Lesson[]>(`${API_BASE_URL}${path}`, { signal })
  if (!Array.isArray(lessons)) {
    throw new ApiError(0, "Сервис вернул расписание в неизвестном формате.")
  }
  return lessons
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return "Не удалось выполнить запрос. Попробуй ещё раз."
}
