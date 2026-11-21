import type {
  AvailableClassroomFilters,
  Classroom,
  ClassroomFilters,
  ClassroomInput,
  Group,
  GroupFilters,
  GroupInput,
  Lesson,
  LessonInput,
  LoginInput,
  Readiness,
  Subject,
  SubjectFilters,
  SubjectInput,
  Teacher,
  TeacherFilters,
  TeacherInput,
  TimeSlot,
  TimeSlotFilters,
  TokenResponse,
  User,
  UserCreateInput,
  UserUpdateInput,
} from "@/lib/models"

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "")
const healthDefault = new URL(API_BASE_URL, window.location.origin).origin + "/health/ready"
const HEALTH_URL = import.meta.env.VITE_HEALTH_URL || healthDefault
export const ACCESS_TOKEN_STORAGE_KEY = "schedule_service_access_token"

type UnauthorizedHandler = () => void
let unauthorizedHandler: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler
}

export function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setAccessToken(token: string): void {
  try {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token)
  } catch {
    // Storage can be unavailable in restricted contexts.
  }
}

export function clearAccessToken(): void {
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    // Ignore storage cleanup failures.
  }
}

interface ValidationIssue {
  loc: (string | number)[]
  msg: string
}

const conflictTypeLabels: Record<string, string> = {
  TEACHER_BUSY: "Преподаватель уже занят в выбранный временной слот",
  GROUP_BUSY: "Учебная группа уже занята в выбранный временной слот",
  CLASSROOM_BUSY: "Аудитория уже занята в выбранный временной слот",
  CAPACITY_EXCEEDED: "Вместимость аудитории недостаточна для выбранной группы",
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

async function responseError(
  response: Response,
  options: { isLogin?: boolean } = {},
): Promise<ApiError> {
  let detail: unknown
  let conflicts: unknown
  try {
    const body: unknown = await response.json()
    if (body && typeof body === "object") {
      if ("detail" in body) {
        detail = body.detail
      }
      if ("conflicts" in body) {
        conflicts = body.conflicts
      } else if (detail && typeof detail === "object" && "conflicts" in detail) {
        conflicts = detail.conflicts
      }
    }
  } catch {
    // Proxies can return HTML instead of FastAPI's JSON error body.
  }
  const messages: Record<number, string> = {
    401: options.isLogin
      ? "Неверный логин или пароль, либо аккаунт заблокирован."
      : "Сессия истекла или недействительна. Войди в систему повторно.",
    403: "Недостаточно прав для выполнения этого действия.",
    404: "Запись не найдена. Возможно, её уже удалили. Обнови список.",
    409: "Не удалось сохранить: запись с такими данными уже существует или связана с расписанием.",
    422: "Проверь значения полей формы.",
    503: "Сервис временно недоступен. Попробуй ещё раз позже.",
  }
  if (response.status === 409 && detail === "Username already exists") {
    messages[409] = "Пользователь с таким логином уже существует."
  }
  if (response.status === 409 && Array.isArray(conflicts) && conflicts.length > 0) {
    const reasons = Array.from(
      new Set(
        conflicts.map((item) => {
          if (
            item &&
            typeof item === "object" &&
            "conflict_type" in item &&
            typeof item.conflict_type === "string"
          ) {
            return conflictTypeLabels[item.conflict_type] || item.conflict_type
          }
          return "Накладка в расписании"
        }),
      ),
    )
    messages[409] = `Обнаружена коллизия расписания: ${reasons.join("; ")}.`
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

interface RequestOptions extends RequestInit {
  skipAuth?: boolean
  isLogin?: boolean
  suppressUnauthorizedEvent?: boolean
}

export async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { skipAuth, isLogin, suppressUnauthorizedEvent, ...fetchOptions } = options
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 15000)
  let signal = controller.signal
  if (fetchOptions.signal) {
    signal = AbortSignal.any([fetchOptions.signal, controller.signal])
  }
  const token = skipAuth ? null : getAccessToken()
  const headers = new Headers(fetchOptions.headers)
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json")
  }
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`)
  }
  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal,
      headers,
    })
    if (!response.ok) {
      const error = await responseError(response, { isLogin })
      if (response.status === 401 && !isLogin && !suppressUnauthorizedEvent && token) {
        clearAccessToken()
        unauthorizedHandler?.()
      }
      throw error
    }
    if (response.status === 204) {
      return undefined as T
    }
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    if (signal.aborted && fetchOptions.signal?.aborted) {
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

export const authApi = {
  login: (input: LoginInput) =>
    request<TokenResponse>(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      skipAuth: true,
      isLogin: true,
    }),
  logout: () =>
    request<void>(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      suppressUnauthorizedEvent: true,
    }),
  me: (signal?: AbortSignal) =>
    request<User>(`${API_BASE_URL}/auth/me`, {
      signal,
      suppressUnauthorizedEvent: true,
    }),
}

export const usersApi = {
  list: async (signal?: AbortSignal) => {
    const records = await request<User[]>(`${API_BASE_URL}/users`, { signal })
    if (!Array.isArray(records)) {
      throw new ApiError(0, "Сервис вернул список пользователей в неизвестном формате.")
    }
    return records
  },
  create: (input: UserCreateInput) =>
    request<User>(`${API_BASE_URL}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  update: (id: number, input: UserUpdateInput) =>
    request<User>(`${API_BASE_URL}/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
}

export const groupsApi = createResource<Group, GroupInput, GroupFilters>("groups")
export const teachersApi = createResource<Teacher, TeacherInput, TeacherFilters>("teachers")
export const classroomsApi = createResource<Classroom, ClassroomInput, ClassroomFilters>(
  "classrooms",
)
export const subjectsApi = createResource<Subject, SubjectInput, SubjectFilters>("subjects")
export const timeSlotsApi = createResource<TimeSlot, never, TimeSlotFilters>("time-slots")
export const lessonsApi = createResource<Lesson, LessonInput, Record<string, unknown>>("lessons")

export const getAvailableClassrooms = async (
  filters: AvailableClassroomFilters,
  signal?: AbortSignal,
) => {
  const records = await request<Classroom[]>(
    `${API_BASE_URL}/schedule/classrooms/available?${queryString(filters)}`,
    { signal },
  )
  if (!Array.isArray(records)) {
    throw new ApiError(0, "Сервис вернул список аудиторий в неизвестном формате.")
  }
  return records
}

export const getReadiness = (signal?: AbortSignal) =>
  request<Readiness>(HEALTH_URL, { signal, skipAuth: true })

export const getLessons = async (signal?: AbortSignal) => {
  const path = import.meta.env.VITE_SCHEDULE_PATH || "/lessons/"
  const lessons = await request<Lesson[]>(`${API_BASE_URL}${path}`, { signal })
  if (!Array.isArray(lessons)) {
    throw new ApiError(0, "Сервис вернул расписание в неизвестном формате.")
  }
  return lessons
}

export async function downloadExportFile(path: string, fallbackFilename: string): Promise<void> {
  const token = getAccessToken()
  const headers = new Headers()
  if (token) {
    headers.set("Authorization", `Bearer ${token}`)
  }
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { headers })
  } catch {
    throw new ApiError(0, "Нет связи с сервером. Проверь подключение и повтори запрос.")
  }
  if (!response.ok) {
    const error = await responseError(response)
    if (response.status === 401 && token) {
      clearAccessToken()
      unauthorizedHandler?.()
    }
    throw error
  }
  const disposition = response.headers.get("content-disposition") || ""
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/i)
  const filename = filenameMatch?.[1] || fallbackFilename
  const blob = await response.blob()
  const objectUrl = window.URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000)
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return "Не удалось выполнить запрос. Попробуй ещё раз."
}
